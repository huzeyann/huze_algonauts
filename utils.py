import functools
import os
import pathlib
import pickle
import re
import subprocess

import numpy as np
from PIL import Image

# import cv2

import glob
import torch
from tqdm import tqdm
from torch import nn


class TensorCenterCrop(object):

    def __init__(self, crop_size: int) -> None:
        self.crop_size = crop_size

    def __call__(self, tensor: torch.FloatTensor) -> torch.FloatTensor:
        H, W = tensor.size(-2), tensor.size(-1)
        from_H = ((H - self.crop_size) // 2)
        from_W = ((W - self.crop_size) // 2)
        to_H = from_H + self.crop_size
        to_W = from_W + self.crop_size
        return tensor[..., from_H:to_H, from_W:to_W]


def disable_bn(model):
    for module in model.modules():
        if isinstance(module, nn.BatchNorm3d):
            module.eval()


def vectorized_correlation(x, y):
    dim = 0

    centered_x = x - x.mean(dim, keepdims=True)
    centered_y = y - y.mean(dim, keepdims=True)

    covariance = (centered_x * centered_y).sum(dim, keepdims=True)

    bessel_corrected_covariance = covariance / (x.shape[dim] - 1)

    x_std = x.std(dim, keepdims=True) + 1e-8
    y_std = y.std(dim, keepdims=True) + 1e-8

    corr = bessel_corrected_covariance / (x_std * y_std)

    return corr.ravel()


def dokodemo_hsplit(x, idxs):
    ret = []
    for i in range(len(idxs)):
        if i == 0:
            ret.append(x[:, :idxs[i]])
        else:
            ret.append(x[:, idxs[i - 1]:idxs[i]])
    return ret


def roi_correlation(x, y, roi_keys, roi_idx):
    xx = hsplit(x, roi_idx)
    yy = hsplit(y, roi_idx)
    subs = np.unique(roi_keys[:, 1])
    rois = np.unique(roi_keys[:, 0])

    corrs_dict = {}
    roi_mean_corr_dict = {}
    i = 0
    for roi in rois:
        sub_corrs = {}
        for sub in subs:
            a, b = xx[i], yy[i]
            corr = vectorized_correlation(a, b).mean().item()
            sub_corrs[sub] = corr
            i += 1
        corrs_dict[roi] = sub_corrs
        roi_mean_corr_dict[roi] = np.mean(list(sub_corrs.values()))

    return corrs_dict, roi_mean_corr_dict, np.mean(list(roi_mean_corr_dict.values()))


def roi_results(x, roi_keys, roi_idx):
    xx = hsplit(x, roi_idx)
    subs = np.unique(roi_keys[:, 1])
    rois = np.unique(roi_keys[:, 0])

    results = {}
    i = 0
    for roi in rois:
        sub_results = {}
        for sub in subs:
            sub_results[sub] = xx[i].cpu().numpy()
            i += 1
        results[roi] = sub_results

    return results


def extract_frames(video_file, num_frames=8):
    """Return a list of PIL image frames uniformly sampled from an mp4 video."""
    try:
        os.makedirs(os.path.join(os.getcwd(), 'frames'))
    except OSError:
        pass
    output = subprocess.Popen(['ffmpeg', '-i', video_file],
                              stderr=subprocess.PIPE).communicate()
    # Search and parse 'Duration: 00:05:24.13,' from ffmpeg stderr.
    re_duration = re.compile(r'Duration: (.*?)\.')
    duration = re_duration.search(str(output[1])).groups()[0]

    seconds = functools.reduce(lambda x, y: x * 60 + y,
                               map(int, duration.split(':')))
    rate = num_frames / float(seconds)

    output = subprocess.Popen(['ffmpeg', '-i', video_file,
                               '-vf', 'fps={}'.format(rate),
                               '-vframes', str(num_frames),
                               '-loglevel', 'panic',
                               'frames/%d.jpg']).communicate()
    frame_paths = sorted([os.path.join('frames', frame)
                          for frame in os.listdir('frames')])
    frames = load_frames(frame_paths, num_frames=num_frames)
    subprocess.call(['rm', '-rf', 'frames'])
    return frames


def load_frames(frame_paths, num_frames=8):
    """Load PIL images from a list of file paths."""
    frames = [Image.open(frame).convert('RGB') for frame in frame_paths]
    if len(frames) >= num_frames:
        return frames[::int(np.ceil(len(frames) / float(num_frames)))]
    else:
        raise ValueError('Video must have at least {} frames'.format(num_frames))


# def render_frames(frames, prediction):
#     """Write the predicted category in the top-left corner of each frame."""
#     rendered_frames = []
#     for frame in frames:
#         img = np.array(frame)
#         height, width, _ = img.shape
#         cv2.putText(img, prediction,
#                     (1, int(height / 8)),
#                     cv2.FONT_HERSHEY_SIMPLEX,
#                     1, (255, 255, 255), 2)
#         rendered_frames.append(img)
#     return rendered_frames


def load_dict(filename_):
    with open(filename_, 'rb') as f:
        u = pickle._Unpickler(f)
        u.encoding = 'latin1'
        ret_di = u.load()
        # print(p)
        # ret_di = pickle.load(f)
    return ret_di


def get_fmri(fmri_dir, ROI):
    """This function loads fMRI data into a numpy array for to a given ROI.

    Parameters
    ----------
    fmri_dir : str
        path to fMRI data.
    ROI : str
        name of ROI.

    Returns
    -------
    np.array
        matrix of dimensions #train_vids x #repetitions x #voxels
        containing fMRI responses to train videos of a given ROI

    """

    # Loading ROI data
    ROI_file = os.path.join(fmri_dir, ROI + ".pkl")
    ROI_data = load_dict(ROI_file)

    # averaging ROI data across repetitions
    ROI_data_train = np.mean(ROI_data["train"], axis=1)
    if ROI == "WB":
        voxel_mask = ROI_data['voxel_mask']
        return ROI_data_train, voxel_mask

    return ROI_data_train


def concat_and_mask(lst, axis=-1):
    len_list = [x.shape[axis] for x in lst]
    arr = np.concatenate(lst, axis=axis)
    idx_ends = np.cumsum(len_list)
    # idex_ends for np.hsplit
    return arr, idx_ends


def load_fmri(base_fmri_dir, rois, subs):
    # rois = ['LOC', 'FFA', 'STS', 'EBA', 'PPA', 'V1', 'V2', 'V3', 'V4']
    # subs = ['sub01', 'sub02', 'sub03', 'sub04', 'sub05', 'sub06', 'sub07', 'sub08', 'sub09', 'sub10']
    track = "mini_track" if 'WB' not in rois else "full_track"
    from itertools import product
    comb = product(rois, subs)

    fmri_dict = {
        (roi, sub): get_fmri(os.path.join(base_fmri_dir, track, sub), roi)
        for roi, sub in comb
    }

    all_fmri, idx_ends = concat_and_mask(list(fmri_dict.values()))
    keys = np.asarray(list(fmri_dict.keys()))
    lens = [v.shape[1] for v in fmri_dict.values()]

    return all_fmri, keys, idx_ends, lens


def load_fmri_wb(base_fmri_dir, roi, subs):
    # rois = ['WB']
    # subs = ['sub01', 'sub02', 'sub03', 'sub04', 'sub05', 'sub06', 'sub07', 'sub08', 'sub09', 'sub10']
    track = "full_track"
    from itertools import product

    fmri_dict = {
        sub: get_fmri(os.path.join(base_fmri_dir, track, sub), roi)
        for sub in subs
    }

    return fmri_dict


def load_videos(video_dir, transform, num_segments=16):
    video_list = glob.glob(video_dir + '/*.mp4')
    video_list.sort()

    videos = []
    for video_file in tqdm(video_list):
        frames = extract_frames(video_file, num_segments)
        input = torch.stack([transform(frame) for frame in frames], 1)
        videos.append(input)
    videos = torch.stack(videos, 0)
    return videos


def warp_load_video(video_dir, transform, num_segments=16):
    video_cache_path = f'./videos.pkl{num_segments}'
    local_cache_path = os.path.join('/data/huze/.cache/',
                                    os.path.basename(video_cache_path))
    if not os.path.exists(video_cache_path):
        videos = load_videos(video_dir, transform, num_segments)
        torch.save(videos, video_cache_path)
        if not os.path.exists(local_cache_path):
            os.system(f'cp {video_cache_path} {local_cache_path}')
    else:
        if not os.path.exists(local_cache_path):
            os.system(f'cp {video_cache_path} {local_cache_path}')
        videos = torch.load(local_cache_path)
    return videos


def save_fn(obj, save_dir, file_name):
    if not os.path.exists(save_dir):
        os.mkdir(save_dir)
    torch.save(obj, os.path.join(save_dir, file_name))


def save_fn_np(arr, save_dir, file_name):
    if not os.path.exists(save_dir):
        os.mkdir(save_dir)
    np.save(os.path.join(save_dir, file_name), arr)


def load_categories(filename):
    """Load categories."""
    with open(filename) as f:
        return [line.rstrip() for line in f.readlines()]


def save_video(rgb_vid, video_path, fps=5):
    import cv2

    image_folder = '/tmp/frames/'
    os.makedirs(image_folder, exist_ok=True)

    for i in range(rgb_vid.shape[0]):
        im = Image.fromarray(rgb_vid[i])
        im.save(f"/tmp/frames/{i}.png")

    images = [img for img in os.listdir(image_folder) if img.endswith(".png")]
    frame = cv2.imread(os.path.join(image_folder, images[0]))
    height, width, layers = frame.shape

    video = cv2.VideoWriter(video_path, 0, fps, (width, height))

    for image in images:
        video.write(cv2.imread(os.path.join(image_folder, image)))

    cv2.destroyAllWindows()
    video.release()


def reject_outliers(data, m=2):
    new_data = np.zeros(data.shape)
    idx = abs(data - np.mean(data)) < m * np.std(data)
    new_data[idx] = data[idx]
    return new_data


def reject_outliers_torch(data, m=2):
    new_data = torch.zeros(data.shape, device=data.device)
    idx = abs(data - torch.mean(data)) < m * torch.std(data)
    new_data[idx] = data[idx]
    return new_data


def which_ffmpeg() -> str:
    '''Determines the path to ffmpeg library

    Returns:
        str -- path to the library
    '''
    result = subprocess.run(['which', 'ffmpeg'], stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    ffmpeg_path = result.stdout.decode('utf-8').replace('\n', '')
    return ffmpeg_path


def reencode_video_with_diff_fps(video_path: str, tmp_path: str, extraction_fps: int) -> str:
    '''Reencodes the video given the path and saves it to the tmp_path folder.

    Args:
        video_path (str): original video
        tmp_path (str): the folder where tmp files are stored (will be appended with a proper filename).
        extraction_fps (int): target fps value

    Returns:
        str: The path where the tmp file is stored. To be used to load the video from
    '''
    assert which_ffmpeg() != '', 'Is ffmpeg installed? Check if the conda environment is activated.'
    assert video_path.endswith('.mp4'), 'The file does not end with .mp4. Comment this if expected'
    # create tmp dir if doesn't exist
    os.makedirs(tmp_path, exist_ok=True)

    # form the path to tmp directory
    new_path = os.path.join(tmp_path, f'{pathlib.Path(video_path).stem}_new_fps.mp4')
    cmd = f'{which_ffmpeg()} -hide_banner -loglevel panic '
    cmd += f'-y -i {video_path} -t 2.9493087557603688 -filter:v fps=fps={extraction_fps} {new_path}'
    # cmd += f'-y -i {video_path} -t 2.9493087557603688 -filter:v minterpolate {new_path}'
    subprocess.call(cmd.split())
    return new_path