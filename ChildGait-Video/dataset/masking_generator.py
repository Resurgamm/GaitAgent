# --------------------------------------------------------
# Based on BEiT, timm, DINO and DeiT code bases
# https://github.com/microsoft/unilm/tree/master/beit
# https://github.com/rwightman/pytorch-image-models/tree/master/timm
# https://github.com/facebookresearch/deit
# https://github.com/facebookresearch/dino
# --------------------------------------------------------'
import numpy as np


class Cell():

    def __init__(self, num_masks, num_patches):
        self.num_masks = num_masks
        self.num_patches = num_patches
        self.size = num_masks + num_patches
        self.queue = np.hstack([np.ones(num_masks), np.zeros(num_patches)])
        self.queue_ptr = 0

    def set_ptr(self, pos=-1):
        self.queue_ptr = np.random.randint(self.size) if pos < 0 else pos

    def get_cell(self):
        cell_idx = (np.arange(self.size) + self.queue_ptr) % self.size
        return self.queue[cell_idx]

    def run_cell(self):
        self.queue_ptr += 1


class RandomMaskingGenerator:

    def __init__(self, input_size, mask_ratio):
        if not isinstance(input_size, tuple):
            input_size = (input_size, ) * 3

        self.frames, self.height, self.width = input_size

        self.num_patches = self.frames * self.height * self.width  # 8x14x14
        self.num_mask = int(mask_ratio * self.num_patches)

    def __repr__(self):
        repr_str = "Mask: total patches {}, mask patches {}".format(
            self.num_patches, self.num_mask)
        return repr_str

    def __call__(self):
        mask = np.hstack([
            np.zeros(self.num_patches - self.num_mask),
            np.ones(self.num_mask),
        ])
        np.random.shuffle(mask)
        return mask  # [196*8]


class TubeMaskingGenerator:

    def __init__(self, input_size, mask_ratio):
        self.frames, self.height, self.width = input_size
        self.num_patches_per_frame = self.height * self.width  # 14x14
        self.total_patches = self.frames * self.num_patches_per_frame
        self.num_masks_per_frame = int(mask_ratio * self.num_patches_per_frame)
        self.total_masks = self.frames * self.num_masks_per_frame

    def __repr__(self):
        repr_str = "Tube Masking: total patches {}, mask patches {}".format(
            self.total_patches, self.total_masks)
        return repr_str

    def __call__(self):
        mask_per_frame = np.hstack([
            np.zeros(self.num_patches_per_frame - self.num_masks_per_frame),
            np.ones(self.num_masks_per_frame),
        ])
        np.random.shuffle(mask_per_frame)
        mask = np.tile(mask_per_frame, (self.frames, 1))
        return mask  # [196*8]


class RunningCellMaskingGenerator:

    def __init__(self, input_size, mask_ratio=0.5):
        self.frames, self.height, self.width = input_size
        self.mask_ratio = mask_ratio

        num_masks_per_cell = int(4 * self.mask_ratio)
        assert 0 < num_masks_per_cell < 4
        num_patches_per_cell = 4 - num_masks_per_cell

        self.cell = Cell(num_masks_per_cell, num_patches_per_cell)
        self.cell_size = self.cell.size

        mask_list = []
        for ptr_pos in range(self.cell_size):
            self.cell.set_ptr(ptr_pos)
            mask = []
            for _ in range(self.frames):
                self.cell.run_cell()
                mask_unit = self.cell.get_cell().reshape(2, 2)
                mask_map = np.tile(mask_unit,
                                   [self.height // 2, self.width // 2])
                mask.append(mask_map.flatten())
            mask = np.stack(mask, axis=0)
            mask_list.append(mask)
        self.all_mask_maps = np.stack(mask_list, axis=0)

    def __repr__(self):
        repr_str = f"Running Cell Masking with mask ratio {self.mask_ratio}"
        return repr_str

    def __call__(self):
        mask = self.all_mask_maps[np.random.randint(self.cell_size)]
        return np.copy(mask)


def bbox_to_patch_mask(bboxes, orig_h, orig_w, short_side_size, crop_size,
                       patch_size, num_frames, tubelet_size,
                       crop_x_offset=None, crop_y_offset=None):
    """Compute a boolean keep_mask from per-frame bounding boxes.

    Each frame has its own bbox. For each temporal token t we take the union
    of bboxes of the frames in that tube (t*tubelet_size : (t+1)*tubelet_size),
    then compute which spatial patches overlap that union. So the mask can
    differ per temporal position.

    Args:
        bboxes: list of length num_frames; each element is [x, y, w, h] in
            original pixel coords for that frame, or None if no bbox.
        orig_h, orig_w: original video resolution (height, width).
        short_side_size: target size for the short-side resize.
        crop_size: spatial size after center-crop (typically == short_side_size).
        patch_size: (patch_h, patch_w) tuple from the ViT backbone.
        num_frames: number of frames fed to the model (must equal len(bboxes)).
        tubelet_size: temporal grouping factor.
        crop_x_offset: explicit x crop offset.  When None, center-crop is used.
        crop_y_offset: explicit y crop offset.  When None, center-crop is used.

    Returns:
        keep_mask – bool np.ndarray of shape [T_patches * H_patches * W_patches].
            Order: time first, then space (t, r, c). True = keep, False = drop.
    """
    ph, pw = patch_size
    h_patches = crop_size // ph
    w_patches = crop_size // pw
    t_patches = num_frames // tubelet_size

    if len(bboxes) != num_frames:
        raise ValueError(
            'bboxes must have length num_frames (one bbox per frame), '
            'got len(bboxes)=%d, num_frames=%d' % (len(bboxes), num_frames))

    short_side = min(orig_h, orig_w)
    scale = short_side_size / short_side
    new_h = int(round(orig_h * scale))
    new_w = int(round(orig_w * scale))

    if crop_x_offset is None:
        x_off = int(round((new_w - crop_size) / 2.0))
    else:
        x_off = crop_x_offset
    if crop_y_offset is None:
        y_off = int(round((new_h - crop_size) / 2.0))
    else:
        y_off = crop_y_offset

    def bbox_to_crop_rect(bx, by, bw, bh):
        bx1 = bx * scale - x_off
        by1 = by * scale - y_off
        bx2 = (bx + bw) * scale - x_off
        by2 = (by + bh) * scale - y_off
        bx1 = max(bx1, 0.0)
        by1 = max(by1, 0.0)
        bx2 = min(bx2, float(crop_size))
        by2 = min(by2, float(crop_size))
        return (bx1, by1, bx2, by2)

    def overlap_mask_for_rect(ux1, uy1, ux2, uy2):
        out = np.ones((h_patches, w_patches), dtype=bool)
        if ux1 >= ux2 or uy1 >= uy2:
            return out
        out[:] = False
        for r in range(h_patches):
            for c in range(w_patches):
                p_y1 = r * ph
                p_y2 = p_y1 + ph
                p_x1 = c * pw
                p_x2 = p_x1 + pw
                if (p_x2 > ux1 and p_x1 < ux2 and
                        p_y2 > uy1 and p_y1 < uy2):
                    out[r, c] = True
        return out

    spatial_keep_list = []
    for t in range(t_patches):
        start = t * tubelet_size
        end = (t + 1) * tubelet_size
        tube_bboxes = bboxes[start:end]
        union_x1, union_y1 = float('inf'), float('inf')
        union_x2, union_y2 = -float('inf'), -float('inf')
        for bbox in tube_bboxes:
            if bbox is None:
                continue
            bx, by, bw, bh = bbox
            bx1, by1, bx2, by2 = bbox_to_crop_rect(bx, by, bw, bh)
            if bx2 > bx1 and by2 > by1:
                union_x1 = min(union_x1, bx1)
                union_y1 = min(union_y1, by1)
                union_x2 = max(union_x2, bx2)
                union_y2 = max(union_y2, by2)
        sk = overlap_mask_for_rect(union_x1, union_y1, union_x2, union_y2)
        spatial_keep_list.append(sk)

    # [T_patches, H_patches, W_patches] -> flatten time first
    spatial_keep = np.stack(spatial_keep_list, axis=0)
    keep_mask = spatial_keep.reshape(-1)
    return keep_mask
