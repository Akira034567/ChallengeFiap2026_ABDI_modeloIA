import torch
import numpy as np
import cv2


def pixel2cam(pixel_coord, f, c):
    x = (pixel_coord[:, 0] - c[0]) / f[0] * pixel_coord[:, 2]
    y = (pixel_coord[:, 1] - c[1]) / f[1] * pixel_coord[:, 2]
    z = pixel_coord[:, 2]
    cam_coord = np.concatenate((x[:, None], y[:, None], z[:, None]), 1)
    return cam_coord


def box_to_center_scale(x, y, w, h, aspect_ratio=0.75, scale_mult=1.25):
    pixel_std = 1
    center = np.zeros((2), dtype=np.float32)
    center[0] = x + w * 0.5
    center[1] = y + h * 0.5

    if w > aspect_ratio * h:
        h = w / aspect_ratio
    elif w < aspect_ratio * h:
        w = h * aspect_ratio
    scale = np.array(
        [w * 1.0 / pixel_std, h * 1.0 / pixel_std], dtype=np.float32)
    if center[0] != -1:
        scale = scale * scale_mult
    bbox = [center[0] - scale[0]*0.5, center[1] - scale[1]*0.5, scale[0], scale[1]] # new box
    return center, scale, bbox


def get_affine_transform(center,
                         scale,
                         rot,
                         output_size,
                         shift=np.array([0, 0], dtype=np.float32),
                         inv=0,
                         align=False):
    if not isinstance(scale, np.ndarray) and not isinstance(scale, list):
        scale = np.array([scale, scale])

    scale_tmp = scale
    src_w = scale_tmp[0]
    dst_w = output_size[0]
    dst_h = output_size[1]

    src_dir = [0, src_w * -0.5]
    dst_dir = np.array([0, dst_w * -0.5], np.float32)

    src = np.zeros((3, 2), dtype=np.float32)
    dst = np.zeros((3, 2), dtype=np.float32)
    src[0, :] = center + scale_tmp * shift
    src[1, :] = center + src_dir + scale_tmp * shift
    dst[0, :] = [dst_w * 0.5, dst_h * 0.5]
    dst[1, :] = np.array([dst_w * 0.5, dst_h * 0.5]) + dst_dir
    
    def get_3rd_point(a, b):
        """Return vector c that perpendicular to (a - b)."""
        direct = a - b
        return b + np.array([-direct[1], direct[0]], dtype=np.float32)

    src[2:, :] = get_3rd_point(src[0, :], src[1, :])
    dst[2:, :] = get_3rd_point(dst[0, :], dst[1, :])

    if inv:
        trans = cv2.getAffineTransform(np.float32(dst), np.float32(src))
    else:
        trans = cv2.getAffineTransform(np.float32(src), np.float32(dst))

    return trans


def ProcessBox(box, img, input_size):
    if len(box) == 4:
        xmin, ymin, xmax, ymax = box
    else:
        xmin, ymin = box[0]
        xmax, ymax = box[1]
    w = xmax - xmin
    h = ymax - ymin
    center, scale, bbox = box_to_center_scale(xmin, ymin, w, h, input_size[0]/input_size[1])
    trans = get_affine_transform(center, scale, 0, input_size)
    img = cv2.warpAffine(img, trans, (int(input_size[0]), int(input_size[1])), flags=cv2.INTER_LINEAR)
    
    #cv2.imwrite('person_' + str(person_idx) + '_input.png', img)

    img = np.transpose(cv2.cvtColor(img, cv2.COLOR_BGR2RGB), (2, 0, 1))  # C*H*W
    img = torch.from_numpy(img).float()
    
    if img.max() > 1:
        img /= 255
    # mean
    img[0].add_(-0.406)
    img[1].add_(-0.457)
    img[2].add_(-0.480)
    # std
    img[0].div_(0.225)
    img[1].div_(0.224)
    img[2].div_(0.229)
    
    return img, bbox


def transform_preds(coords, center, scale, output_size):
    target_coords = np.zeros(coords.shape)
    trans = get_affine_transform(center, scale, 0, output_size, inv=1)
    
    def affine_transform(pt, t):
        new_pt = np.array([pt[0], pt[1], 1.]).T
        new_pt = np.dot(t, new_pt)
        return new_pt[:2]
    
    target_coords[0:2] = affine_transform(coords[0:2], trans)
    return target_coords


# Convert to original image coordinate system
def pre2coord(pred_jts, img_shape, bbox, output_3d):
    img_width, img_height = img_shape

    coords = pred_jts.astype(float)
    coords[:, 0] = (coords[:, 0] + 0.5) * img_width
    coords[:, 1] = (coords[:, 1] + 0.5) * img_height
    preds = np.zeros_like(coords)
    # transform bbox to scale
    xmin, ymin, w, h = bbox
    center = np.array([xmin + w * 0.5, ymin + h * 0.5])
    scale = np.array([w, h])
    # Transform back
    for j in range(coords.shape[0]):
        preds[j, 0:2] = transform_preds(coords[j, 0:2], center, scale,
                                            [img_width, img_height])
        if output_3d:
            preds[j, 2] = coords[j, 2] - coords[0, 2]

    return preds # batch size is 1