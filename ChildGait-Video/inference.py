"""Single-video inference for ChildGait VideoMAE fine-tuned models.

Inputs: video path + checkpoint weights.
No bbox / keypoint / keep_mask is used; the full patch sequence is forwarded.
Defaults align with ``scripts/finetune/my_ft.sh`` and validation preprocessing
in ``dataset/datasets.py``.
"""

import argparse
import json
import os
from collections import OrderedDict

import numpy as np
import torch
import torch.nn.functional as F
from timm.models import create_model

# Registers vit_* models with timm
import models  # noqa: F401
from dataset import video_transforms, volume_transforms
from dataset.loader import get_video_loader


IMAGENET_MEAN = [0.485, 0.456, 0.406]
IMAGENET_STD = [0.229, 0.224, 0.225]


def get_args():
    parser = argparse.ArgumentParser(
        'ChildGait VideoMAE single-video inference (no mask/keypoints)')
    parser.add_argument(
        '--video', required=True, type=str, help='path to input video')
    parser.add_argument(
        '--ckpt',
        '--finetune',
        dest='ckpt',
        required=True,
        type=str,
        help='path to model checkpoint (.pth)')
    parser.add_argument(
        '--model',
        default='vit_giant_patch14_224',
        type=str,
        help='model name (must match training)')
    parser.add_argument('--nb_classes', default=2, type=int)
    parser.add_argument('--input_size', default=224, type=int)
    parser.add_argument('--short_side_size', default=224, type=int)
    parser.add_argument('--num_frames', default=32, type=int)
    parser.add_argument('--sampling_rate', default=2, type=int)
    parser.add_argument('--tubelet_size', default=2, type=int)
    parser.add_argument('--num_segments', default=1, type=int)
    parser.add_argument('--drop_path', default=0.1, type=float)
    parser.add_argument(
        '--with_checkpoint',
        action='store_true',
        default=False,
        help='enable gradient checkpointing modules (match training if used)')
    parser.add_argument(
        '--model_key',
        default='model|module|state_dict',
        type=str,
        help='checkpoint dict keys to try, separated by |')
    parser.add_argument(
        '--device',
        default='cuda' if torch.cuda.is_available() else 'cpu',
        type=str,
        help='cpu / cuda / cuda:N; falls back to cpu if CUDA is unavailable')
    parser.add_argument(
        '--output',
        default=None,
        type=str,
        help='optional path to save json result')
    parser.add_argument(
        '--return_features',
        action='store_true',
        default=False,
        help='also return pooled features before the classification head')
    return parser.parse_args()


def resolve_device(device_str):
    """Return a usable torch.device; fall back to CPU if CUDA is missing."""
    if device_str.startswith('cuda') and not torch.cuda.is_available():
        print(
            f'Warning: requested --device {device_str} but CUDA is unavailable '
            f'(no NVIDIA driver / GPU). Falling back to cpu.')
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
            index = np.linspace(0, seg_len, num=max(seg_len // frame_sample_rate, 1))
            pad = clip_len - len(index)
            if pad > 0:
                index = np.concatenate((index, np.ones(pad) * max(seg_len - 1, 0)))
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
    # C T H W
    tensor = transform(buffer)
    return tensor.unsqueeze(0)  # 1 C T H W


def load_checkpoint(model, ckpt_path, model_key='model|module|state_dict'):
    # PyTorch>=2.6 defaults weights_only=True; finetune ckpts may embed numpy scalars.
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
        raise RuntimeError(f'Unexpected checkpoint format: {type(checkpoint_model)}')

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
        if k in checkpoint_model and checkpoint_model[k].shape != state_dict[k].shape:
            print(f'Removing key {k} from checkpoint (shape mismatch)')
            del checkpoint_model[k]

    msg = model.load_state_dict(checkpoint_model, strict=False)
    print(msg)
    return model


def build_model(args):
    model = create_model(
        args.model,
        img_size=args.input_size,
        pretrained=False,
        num_classes=args.nb_classes,
        all_frames=args.num_frames * args.num_segments,
        tubelet_size=args.tubelet_size,
        drop_path_rate=args.drop_path,
        use_mean_pooling=True,
        with_cp=args.with_checkpoint,
    )
    model = load_checkpoint(model, args.ckpt, model_key=args.model_key)
    model.eval()
    model.to(args.device)
    return model


@torch.no_grad()
def infer(model, video_tensor, device, return_features=False):
    video_tensor = video_tensor.to(device, non_blocking=True)
    # No keep_mask / keypoints: full token sequence
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


def main():
    args = get_args()
    if not os.path.isfile(args.video):
        raise FileNotFoundError(f'Video not found: {args.video}')
    if not os.path.isfile(args.ckpt):
        raise FileNotFoundError(f'Checkpoint not found: {args.ckpt}')

    print(args)
    device = resolve_device(args.device)
    args.device = str(device)

    video_tensor = load_and_preprocess_video(
        args.video,
        clip_len=args.num_frames,
        frame_sample_rate=args.sampling_rate,
        crop_size=args.input_size,
        short_side_size=args.short_side_size,
        num_segment=args.num_segments,
    )
    print(f'Input tensor shape: {tuple(video_tensor.shape)}')

    model = build_model(args)
    result = infer(
        model,
        video_tensor,
        device,
        return_features=args.return_features,
    )

    print('logits:', result['logits'])
    print('probs :', result['probs'])
    print('pred  :', result['pred'])

    if args.output:
        out_dir = os.path.dirname(args.output)
        if out_dir:
            os.makedirs(out_dir, exist_ok=True)
        payload = {
            'video': os.path.abspath(args.video),
            'ckpt': os.path.abspath(args.ckpt),
            'model': args.model,
            'nb_classes': args.nb_classes,
            'num_frames': args.num_frames,
            'sampling_rate': args.sampling_rate,
            **result,
        }
        with open(args.output, 'w') as f:
            json.dump(payload, f, indent=2)
        print(f'Saved result to {args.output}')


if __name__ == '__main__':
    main()
