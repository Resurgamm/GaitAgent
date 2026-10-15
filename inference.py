"""ChildGait VideoMAE inference — local CLI + SageMaker single-endpoint.

SageMaker: one endpoint, discover all ``*.pth`` under ``model_dir``, reuse one
model skeleton, sequentially swap weights, run inference, return per-ckpt results.

Local CLI still works:
  python inference.py --video x.mp4 --ckpt a.pth
  python inference.py --video x.mp4 --ckpt_dir ./saved_models
"""

from __future__ import annotations

import argparse
import base64
import io
import json
import os
import tempfile
from collections import OrderedDict
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

import numpy as np
import torch
import torch.nn.functional as F
from timm.models import create_model

# Registers vit_* models with timm (must ship under code/)
import models  # noqa: F401
from dataset import video_transforms, volume_transforms
from dataset.loader import get_video_loader


IMAGENET_MEAN = [0.485, 0.456, 0.406]
IMAGENET_STD = [0.229, 0.224, 0.225]

# Defaults aligned with finetune / validation preprocessing
DEFAULT_CFG = {
    'model': 'vit_giant_patch14_224',
    'nb_classes': 2,
    'input_size': 224,
    'short_side_size': 224,
    'num_frames': 32,
    'sampling_rate': 2,
    'tubelet_size': 2,
    'num_segments': 1,
    'drop_path': 0.1,
    'with_checkpoint': False,
    'model_key': 'model|module|state_dict',
    'return_features': False,
}


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def resolve_device(device_str: Optional[str] = None) -> torch.device:
    if device_str is None:
        device_str = 'cuda' if torch.cuda.is_available() else 'cpu'
    if device_str.startswith('cuda') and not torch.cuda.is_available():
        print(
            f'Warning: requested device {device_str} but CUDA unavailable; '
            f'falling back to cpu.')
        return torch.device('cpu')
    return torch.device(device_str)


def sample_frame_indices(num_frames_total,
                         clip_len,
                         frame_sample_rate,
                         num_segment=1):
    """Center temporal sampling used by VideoClsDataset validation mode."""
    converted_len = int(clip_len * frame_sample_rate)
    seg_len = num_frames_total // num_segment
    all_index = []
    for i in range(num_segment):
        if seg_len <= converted_len:
            index = np.linspace(
                0, seg_len, num=max(seg_len // frame_sample_rate, 1))
            pad = clip_len - len(index)
            if pad > 0:
                index = np.concatenate(
                    (index, np.ones(pad) * max(seg_len - 1, 0)))
            index = np.clip(index, 0, max(seg_len - 1, 0)).astype(np.int64)
        else:
            end_idx = (converted_len + seg_len) // 2
            str_idx = end_idx - converted_len
            index = np.linspace(str_idx, end_idx, num=clip_len)
            index = np.clip(index, str_idx, end_idx - 1).astype(np.int64)
        index = index + i * seg_len
        all_index.extend(list(index))
    return all_index


def load_and_preprocess_video(video_path,
                              clip_len=32,
                              frame_sample_rate=2,
                              crop_size=224,
                              short_side_size=224,
                              num_segment=1):
    video_loader = get_video_loader(use_petrel_backend=False)
    vr = video_loader(video_path)
    length = len(vr)
    if length == 0:
        raise RuntimeError(f'Empty video: {video_path}')

    indices = sample_frame_indices(
        length, clip_len, frame_sample_rate, num_segment=num_segment)
    vr.seek(0)
    buffer = vr.get_batch(indices).asnumpy()  # T H W C, uint8

    transform = video_transforms.Compose([
        video_transforms.Resize(short_side_size, interpolation='bilinear'),
        video_transforms.CenterCrop(size=(crop_size, crop_size)),
        volume_transforms.ClipToTensor(),
        video_transforms.Normalize(mean=IMAGENET_MEAN, std=IMAGENET_STD),
    ])
    tensor = transform(buffer)  # C T H W
    return tensor.unsqueeze(0)  # 1 C T H W


def load_checkpoint(model, ckpt_path, model_key='model|module|state_dict'):
    checkpoint = torch.load(ckpt_path, map_location='cpu', weights_only=False)
    print(f'Load ckpt from {ckpt_path}')

    checkpoint_model = None
    for key in model_key.split('|'):
        if isinstance(checkpoint, dict) and key in checkpoint:
            checkpoint_model = checkpoint[key]
            print(f'Load state_dict by model_key = {key}')
            break
    if checkpoint_model is None:
        checkpoint_model = checkpoint

    if not isinstance(checkpoint_model, dict):
        raise RuntimeError(
            f'Unexpected checkpoint format: {type(checkpoint_model)}')

    for old_key in list(checkpoint_model.keys()):
        if old_key.startswith('_orig_mod.'):
            checkpoint_model[old_key[10:]] = checkpoint_model.pop(old_key)

    sample_key = next(iter(checkpoint_model), '')
    if sample_key.startswith('backbone.'):
        prefix = 'backbone.'
        print(f"Stripping prefix '{prefix}' from checkpoint keys")
        for old_key in list(checkpoint_model.keys()):
            if old_key.startswith(prefix):
                checkpoint_model[old_key[len(prefix):]] = checkpoint_model.pop(
                    old_key)

    new_dict = OrderedDict()
    for key, value in checkpoint_model.items():
        if key.startswith('backbone.'):
            new_dict[key[9:]] = value
        elif key.startswith('encoder.'):
            new_dict[key[8:]] = value
        else:
            new_dict[key] = value
    checkpoint_model = new_dict

    state_dict = model.state_dict()
    for k in ['head.weight', 'head.bias']:
        if (k in checkpoint_model
                and checkpoint_model[k].shape != state_dict[k].shape):
            print(f'Removing key {k} from checkpoint (shape mismatch)')
            del checkpoint_model[k]

    msg = model.load_state_dict(checkpoint_model, strict=False)
    print(msg)
    return model


def create_empty_model(cfg: Dict[str, Any]) -> torch.nn.Module:
    return create_model(
        cfg['model'],
        img_size=cfg['input_size'],
        pretrained=False,
        num_classes=cfg['nb_classes'],
        all_frames=cfg['num_frames'] * cfg['num_segments'],
        tubelet_size=cfg['tubelet_size'],
        drop_path_rate=cfg['drop_path'],
        use_mean_pooling=True,
        with_cp=cfg['with_checkpoint'],
    )


@torch.no_grad()
def infer(model, video_tensor, device, return_features=False):
    video_tensor = video_tensor.to(device, non_blocking=True)
    if device.type == 'cuda':
        with torch.cuda.amp.autocast(dtype=torch.bfloat16):
            features = model.forward_features(video_tensor, keep_mask=None)
            logits = model.head_dropout(features)
            logits = model.head(logits)
    else:
        features = model.forward_features(video_tensor, keep_mask=None)
        logits = model.head_dropout(features)
        logits = model.head(logits)

    logits = logits.float()
    probs = F.softmax(logits, dim=-1)
    pred = int(torch.argmax(probs, dim=-1).item())
    result = {
        'logits': logits.squeeze(0).cpu().tolist(),
        'probs': probs.squeeze(0).cpu().tolist(),
        'pred': pred,
    }
    if return_features:
        result['features'] = features.float().squeeze(0).cpu().tolist()
    return result


def discover_checkpoints(root: Union[str, Path]) -> List[Path]:
    """Find ``*.pth`` under root (root itself or ``saved_models/`` subdir).

    Sort by natural numeric stem when possible (1.pth, 2.pth, ...),
    otherwise lexicographic.
    """
    root = Path(root)
    candidates: List[Path] = []
    search_roots = [root]
    saved_models_dir = root / 'saved_models'
    if saved_models_dir.is_dir():
        search_roots.append(saved_models_dir)

    seen = set()
    for sr in search_roots:
        for p in sr.glob('*.pth'):
            rp = p.resolve()
            if rp not in seen:
                seen.add(rp)
                candidates.append(p)

    def sort_key(p: Path):
        stem = p.stem
        return (0, int(stem)) if stem.isdigit() else (1, stem)

    candidates.sort(key=sort_key)
    return candidates


def sequential_infer(
        model: torch.nn.Module,
        ckpt_paths: List[Path],
        video_tensor: torch.Tensor,
        device: torch.device,
        cfg: Dict[str, Any],
) -> List[Dict[str, Any]]:
    """Load each checkpoint into the same model, infer, collect results."""
    results = []
    for ckpt_path in ckpt_paths:
        load_checkpoint(model, str(ckpt_path), model_key=cfg['model_key'])
        model.eval()
        model.to(device)
        one = infer(
            model,
            video_tensor,
            device,
            return_features=cfg.get('return_features', False),
        )
        one['ckpt'] = ckpt_path.name
        results.append(one)
        if device.type == 'cuda':
            torch.cuda.empty_cache()
    return results


# ---------------------------------------------------------------------------
# SageMaker handlers
# Unpacked layout at /opt/ml/model:
#   /opt/ml/model/1.pth          (or saved_models/1.pth)
#   /opt/ml/model/2.pth
#   /opt/ml/model/code/inference.py
#   /opt/ml/model/code/models/ ...
#   /opt/ml/model/code/dataset/ ...
#   /opt/ml/model/code/requirements.txt
# ---------------------------------------------------------------------------

def model_fn(model_dir: str):
    """Called once at endpoint startup. Build empty model + list ckpts."""
    cfg = dict(DEFAULT_CFG)
    # Optional overrides next to weights
    cfg_path = Path(model_dir) / 'inference_config.json'
    if cfg_path.is_file():
        with open(cfg_path) as f:
            cfg.update(json.load(f))

    device = resolve_device()
    ckpt_paths = discover_checkpoints(model_dir)
    if not ckpt_paths:
        raise RuntimeError(
            f'No .pth found under {model_dir} (or {model_dir}/saved_models)')

    print(f'Device={device}, checkpoints={[p.name for p in ckpt_paths]}')
    model = create_empty_model(cfg)
    model.eval()
    model.to(device)

    return {
        'model': model,
        'ckpt_paths': ckpt_paths,
        'device': device,
        'cfg': cfg,
    }


def input_fn(request_body, content_type: str = 'application/json'):
    """Accept JSON {\"video_b64\": \"...\", ...cfg overrides} or raw video bytes."""
    cfg_overrides: Dict[str, Any] = {}
    video_bytes: Optional[bytes] = None

    if content_type in ('application/json', 'application/json; charset=utf-8'):
        if isinstance(request_body, bytes):
            payload = json.loads(request_body.decode('utf-8'))
        else:
            payload = json.loads(request_body)
        if 'video_b64' not in payload:
            raise ValueError('JSON body must contain video_b64')
        video_bytes = base64.b64decode(payload['video_b64'])
        for k in DEFAULT_CFG:
            if k in payload:
                cfg_overrides[k] = payload[k]
        if 'return_features' in payload:
            cfg_overrides['return_features'] = bool(payload['return_features'])
    elif content_type in (
            'application/octet-stream',
            'video/mp4',
            'video/mpeg',
            'video/quicktime',
    ):
        video_bytes = (request_body if isinstance(request_body, bytes)
                       else request_body.encode('latin1'))
    else:
        raise ValueError(f'Unsupported content_type: {content_type}')

    suffix = '.mp4'
    tmp = tempfile.NamedTemporaryFile(suffix=suffix, delete=False)
    try:
        tmp.write(video_bytes)
        tmp.flush()
        tmp.close()
        video_path = tmp.name
    except Exception:
        tmp.close()
        os.unlink(tmp.name)
        raise

    return {'video_path': video_path, 'cfg_overrides': cfg_overrides}


def predict_fn(input_data, model_ctx):
    cfg = dict(model_ctx['cfg'])
    cfg.update(input_data.get('cfg_overrides') or {})
    video_path = input_data['video_path']

    try:
        video_tensor = load_and_preprocess_video(
            video_path,
            clip_len=cfg['num_frames'],
            frame_sample_rate=cfg['sampling_rate'],
            crop_size=cfg['input_size'],
            short_side_size=cfg['short_side_size'],
            num_segment=cfg['num_segments'],
        )
        results = sequential_infer(
            model_ctx['model'],
            model_ctx['ckpt_paths'],
            video_tensor,
            model_ctx['device'],
            cfg,
        )
        return {
            'num_models': len(results),
            'results': results,
            # Convenience: majority / first-pred summary
            'preds': [r['pred'] for r in results],
        }
    finally:
        try:
            os.unlink(video_path)
        except OSError:
            pass


def output_fn(prediction, accept: str = 'application/json'):
    if accept not in ('application/json', 'application/json; charset=utf-8'):
        raise ValueError(f'Unsupported accept type: {accept}')
    return json.dumps(prediction), accept


# ---------------------------------------------------------------------------
# Local CLI
# ---------------------------------------------------------------------------

def get_args():
    parser = argparse.ArgumentParser(
        'ChildGait VideoMAE inference (local / SageMaker-compatible)')
    parser.add_argument('--video', required=True, type=str)
    g = parser.add_mutually_exclusive_group(required=True)
    g.add_argument('--ckpt', '--finetune', dest='ckpt', type=str,
                   help='single checkpoint')
    g.add_argument('--ckpt_dir', type=str,
                   help='directory of *.pth (or .../saved_models)')
    parser.add_argument('--model', default=DEFAULT_CFG['model'], type=str)
    parser.add_argument('--nb_classes', default=DEFAULT_CFG['nb_classes'],
                        type=int)
    parser.add_argument('--input_size', default=DEFAULT_CFG['input_size'],
                        type=int)
    parser.add_argument('--short_side_size',
                        default=DEFAULT_CFG['short_side_size'], type=int)
    parser.add_argument('--num_frames', default=DEFAULT_CFG['num_frames'],
                        type=int)
    parser.add_argument('--sampling_rate', default=DEFAULT_CFG['sampling_rate'],
                        type=int)
    parser.add_argument('--tubelet_size', default=DEFAULT_CFG['tubelet_size'],
                        type=int)
    parser.add_argument('--num_segments', default=DEFAULT_CFG['num_segments'],
                        type=int)
    parser.add_argument('--drop_path', default=DEFAULT_CFG['drop_path'],
                        type=float)
    parser.add_argument('--with_checkpoint', action='store_true', default=False)
    parser.add_argument('--model_key', default=DEFAULT_CFG['model_key'],
                        type=str)
    parser.add_argument(
        '--device',
        default='cuda' if torch.cuda.is_available() else 'cpu',
        type=str)
    parser.add_argument('--output', default=None, type=str)
    parser.add_argument('--return_features', action='store_true', default=False)
    return parser.parse_args()


def main():
    args = get_args()
    if not os.path.isfile(args.video):
        raise FileNotFoundError(f'Video not found: {args.video}')

    cfg = {k: getattr(args, k) if hasattr(args, k) else v
           for k, v in DEFAULT_CFG.items()}
    cfg['with_checkpoint'] = args.with_checkpoint
    cfg['return_features'] = args.return_features
    cfg['model'] = args.model
    cfg['nb_classes'] = args.nb_classes
    cfg['input_size'] = args.input_size
    cfg['short_side_size'] = args.short_side_size
    cfg['num_frames'] = args.num_frames
    cfg['sampling_rate'] = args.sampling_rate
    cfg['tubelet_size'] = args.tubelet_size
    cfg['num_segments'] = args.num_segments
    cfg['drop_path'] = args.drop_path
    cfg['model_key'] = args.model_key

    device = resolve_device(args.device)
    print(args)

    if args.ckpt:
        if not os.path.isfile(args.ckpt):
            raise FileNotFoundError(f'Checkpoint not found: {args.ckpt}')
        ckpt_paths = [Path(args.ckpt)]
    else:
        ckpt_paths = discover_checkpoints(args.ckpt_dir)
        if not ckpt_paths:
            raise FileNotFoundError(f'No .pth under {args.ckpt_dir}')

    video_tensor = load_and_preprocess_video(
        args.video,
        clip_len=cfg['num_frames'],
        frame_sample_rate=cfg['sampling_rate'],
        crop_size=cfg['input_size'],
        short_side_size=cfg['short_side_size'],
        num_segment=cfg['num_segments'],
    )
    print(f'Input tensor shape: {tuple(video_tensor.shape)}')
    print(f'Checkpoints: {[p.name for p in ckpt_paths]}')

    model = create_empty_model(cfg)
    results = sequential_infer(model, ckpt_paths, video_tensor, device, cfg)

    for r in results:
        print(f"[{r['ckpt']}] pred={r['pred']} probs={r['probs']}")

    payload = {
        'video': os.path.abspath(args.video),
        'num_models': len(results),
        'results': results,
        'preds': [r['pred'] for r in results],
        'model': cfg['model'],
        'nb_classes': cfg['nb_classes'],
        'num_frames': cfg['num_frames'],
        'sampling_rate': cfg['sampling_rate'],
    }
    if args.output:
        out_dir = os.path.dirname(args.output)
        if out_dir:
            os.makedirs(out_dir, exist_ok=True)
        with open(args.output, 'w') as f:
            json.dump(payload, f, indent=2)
        print(f'Saved result to {args.output}')


if __name__ == '__main__':
    main()
