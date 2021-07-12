import os
from functools import partial

import numpy as np

import torch
import torch.nn as nn
import torch.nn.functional as F
import torchvision.models as models
from torchvision import transforms

from pyramidpooling import SpatialPyramidPooling


def conv3x3x3(in_planes, out_planes, stride=1):
    """3x3x3 convolution with padding."""
    return nn.Conv3d(
        in_planes, out_planes, kernel_size=3, stride=stride, padding=1, bias=False
    )


def downsample_basic_block(x, planes, stride):
    out = F.avg_pool3d(x, kernel_size=1, stride=stride)
    zero_pads = torch.Tensor(
        out.size(0), planes - out.size(1),
        out.size(2), out.size(3), out.size(4)).zero_()
    if isinstance(out.data, torch.cuda.FloatTensor):
        zero_pads = zero_pads.cuda()
    out = torch.cat([out.data, zero_pads], dim=1)
    return out


class BasicBlock(nn.Module):
    expansion = 1
    Conv3d = staticmethod(conv3x3x3)

    def __init__(self, inplanes, planes, stride=1, downsample=None):
        super(BasicBlock, self).__init__()
        self.conv1 = self.Conv3d(inplanes, planes, stride)
        self.bn1 = nn.BatchNorm3d(planes)
        self.relu = nn.ReLU(inplace=True)
        self.conv2 = self.Conv3d(planes, planes)
        self.bn2 = nn.BatchNorm3d(planes)
        self.downsample = downsample
        self.stride = stride

    def forward(self, x):
        residual = x

        out = self.conv1(x)
        out = self.bn1(out)
        out = self.relu(out)

        out = self.conv2(out)
        out = self.bn2(out)

        if self.downsample is not None:
            residual = self.downsample(x)

        out += residual
        out = self.relu(out)
        return out


class Bottleneck(nn.Module):
    expansion = 4
    Conv3d = nn.Conv3d

    def __init__(self, inplanes, planes, stride=1, downsample=None):
        super(Bottleneck, self).__init__()
        self.conv1 = self.Conv3d(inplanes, planes, kernel_size=1, bias=False)
        self.bn1 = nn.BatchNorm3d(planes)
        self.conv2 = self.Conv3d(planes, planes, kernel_size=3, stride=stride, padding=1, bias=False)
        self.bn2 = nn.BatchNorm3d(planes)
        self.conv3 = self.Conv3d(planes, planes * 4, kernel_size=1, bias=False)
        self.bn3 = nn.BatchNorm3d(planes * 4)
        self.relu = nn.ReLU(inplace=True)
        self.downsample = downsample
        self.stride = stride

    def forward(self, x):
        residual = x
        out = self.conv1(x)
        out = self.bn1(out)
        out = self.relu(out)

        out = self.conv2(out)
        out = self.bn2(out)
        out = self.relu(out)

        out = self.conv3(out)
        out = self.bn3(out)

        if self.downsample is not None:
            residual = self.downsample(x)

        out += residual
        out = self.relu(out)
        return out


class ResNet3D(nn.Module):
    Conv3d = nn.Conv3d

    def __init__(self, block, layers, shortcut_type='B', num_classes=305):
        self.inplanes = 64
        super(ResNet3D, self).__init__()
        self.conv1 = self.Conv3d(3, 64, kernel_size=7, stride=(1, 2, 2), padding=(3, 3, 3), bias=False)
        self.bn1 = nn.BatchNorm3d(64)
        self.relu = nn.ReLU(inplace=True)
        self.maxpool = nn.MaxPool3d(kernel_size=(3, 3, 3), stride=2, padding=1)
        self.layer1 = self._make_layer(block, 64, layers[0], shortcut_type)
        self.layer2 = self._make_layer(block, 128, layers[1], shortcut_type, stride=2)
        self.layer3 = self._make_layer(block, 256, layers[2], shortcut_type, stride=2)
        self.layer4 = self._make_layer(block, 512, layers[3], shortcut_type, stride=2)
        self.avgpool = nn.AdaptiveAvgPool3d(1)
        self.fc = nn.Linear(512 * block.expansion, num_classes)

        self.init_weights()

    def _make_layer(self, block, planes, blocks, shortcut_type, stride=1):
        downsample = None
        if stride != 1 or self.inplanes != planes * block.expansion:
            if shortcut_type == 'A':
                downsample = partial(
                    downsample_basic_block,
                    planes=planes * block.expansion,
                    stride=stride,
                )
            else:
                downsample = nn.Sequential(
                    self.Conv3d(
                        self.inplanes,
                        planes * block.expansion,
                        kernel_size=1,
                        stride=stride,
                        bias=False,
                    ),
                    nn.BatchNorm3d(planes * block.expansion),
                )

        layers = []
        layers.append(block(self.inplanes, planes, stride, downsample))
        self.inplanes = planes * block.expansion
        for _ in range(1, blocks):
            layers.append(block(self.inplanes, planes))

        return nn.Sequential(*layers)

    def init_weights(self):
        for m in self.modules():
            if isinstance(m, self.Conv3d):
                nn.init.kaiming_normal_(m.weight, mode='fan_out')
            elif isinstance(m, nn.BatchNorm3d):
                m.weight.data.fill_(1)
                m.bias.data.zero_()

    def forward(self, x):
        x = self.conv1(x)
        x = self.bn1(x)
        x = self.relu(x)
        x = self.maxpool(x)
        x = self.layer1(x)
        x = self.layer2(x)
        x = self.layer3(x)
        x = self.layer4(x)

        x = self.avgpool(x)

        x = x.view(x.size(0), -1)
        x = self.fc(x)

        return x


class MiniFC(nn.Module):

    def __init__(self, hparams):
        super(MiniFC, self).__init__()
        self.no_pooling = True if hparams['pooling_mode'] == 'no' else False
        self.global_pooling = hparams['global_pooling']
        if hparams['backbone_type'] == 'x3':
            conv_indim = 1024
        elif hparams['backbone_type'] == 'x4':
            conv_indim = 2048
        elif hparams['backbone_type'] == 'x2':
            conv_indim = 512
        else:
            raise Exception("?")
        self.conv = nn.Sequential(nn.Conv3d(conv_indim, hparams['conv_size'], kernel_size=1, stride=1), )

        if hparams['global_pooling']:
            self.global_avgpool = nn.AdaptiveAvgPool3d(1)
            input_dim = hparams['conv_size']
        else:
            if self.no_pooling:
                if hparams['backbone_type'] == 'x3':
                    input_dim = hparams['conv_size'] * int(hparams['video_frames'] / 8) * \
                                int(hparams['video_size'] / 16) * int(hparams['video_size'] / 16)
                elif hparams['backbone_type'] == 'x4':
                    input_dim = hparams['conv_size'] * int(hparams['video_frames'] / 16) * \
                                int(hparams['video_size'] / 32) * int(hparams['video_size'] / 32)
                elif hparams['backbone_type'] == 'x2':
                    input_dim = hparams['conv_size'] * int(hparams['video_frames'] / 4) * \
                                int(hparams['video_size'] / 8) * int(hparams['video_size'] / 8)
            else:
                if hparams['backbone_type'] == 'x3':
                    levels = np.array([[1, 2, 2], [1, 2, 4], [1, 2, 4]])
                elif hparams['backbone_type'] == 'x4':
                    levels = np.array([[1, 1, 1], [1, 2, 3], [1, 2, 3]])
                elif hparams['backbone_type'] == 'x2':
                    levels = np.array([[1, 2, 4], [1, 2, 4], [1, 2, 4]])
                self.pyramidpool = SpatialPyramidPooling(levels, hparams['pooling_mode'], hparams['softpool'])
                input_dim = hparams['conv_size'] * np.sum(levels[0] * levels[1] * levels[2])

        self.fc = build_fc(hparams, input_dim, hparams['output_size'])

    def forward(self, x):
        x = self.conv(x)
        if not self.global_pooling:
            if not self.no_pooling:
                x = self.pyramidpool(x)
        else:
            x = self.global_avgpool(x)

        x = torch.cat([
            x.reshape(x.shape[0], -1),
        ], 1)

        out = self.fc(x)

        return out


def build_fc(p, input_dim, output_dim):
    activations = {
        'relu': nn.ReLU(),
        'sigmoid': nn.Sigmoid(),
        'tanh': nn.Tanh(),
        'leakyrelu': nn.LeakyReLU(),
        'elu': nn.ELU(),
    }

    module_list = []
    for i in range(p.get(f"num_layers")):
        if i == 0:
            in_size, out_size = input_dim, p.get(f"layer_hidden")
        else:
            in_size, out_size = p.get(f"layer_hidden"), p.get(f"layer_hidden")
        module_list.append(nn.Linear(in_size, out_size))
        if p.get('fc_batch_norm'):
            module_list.append(nn.BatchNorm1d(out_size))
        module_list.append(activations[p.get('activation')])
        module_list.append(nn.Dropout(p.get("dropout_rate")))

    if p.get(f"num_layers") == 0:
        out_size = input_dim

    # last layer
    module_list.append(nn.Linear(out_size, output_dim))

    return nn.Sequential(*module_list)


class Pyramid(nn.Module):

    def __init__(self, hparams):
        super(Pyramid, self).__init__()
        assert hparams.fc_fusion in ['concat', 'avg', 'avgconact']
        self.hparams = hparams
        self.x1_twh = (int(hparams['video_frames'] / 2), int(hparams['video_size'] / 4), int(hparams['video_size'] / 4))
        self.x2_twh = tuple(map(lambda x: int(x / 2), self.x1_twh))
        self.x3_twh = tuple(map(lambda x: int(x / 2), self.x2_twh))
        self.x4_twh = tuple(map(lambda x: int(x / 2), self.x3_twh))
        self.x1_c, self.x2_c, self.x3_c, self.x4_c = 256, 512, 1024, 2048
        self.twh_dict = {'x1': self.x1_twh, 'x2': self.x2_twh, 'x3': self.x3_twh, 'x4': self.x4_twh}
        self.c_dict = {'x1': self.x1_c, 'x2': self.x2_c, 'x3': self.x3_c, 'x4': self.x4_c}

        self.planes = hparams['conv_size']
        self.pyramid_layers = hparams['pyramid_layers'].split(',')  # x1,x2,x3,x4
        self.pyramid_layers.sort()
        self.is_pyramid = False if len(self.pyramid_layers) > 1 else False
        self.pathways = hparams['pathways'].split(',')  # ['topdown', 'bottomup'] aka 'parallel'
        if self.is_pyramid:
            assert len(self.pathways) >= 1
        else:
            assert len(self.pathways) == 0

        # convs
        self.first_convs = nn.ModuleDict({
            x_i: nn.Conv3d(self.c_dict[x_i], self.planes, kernel_size=1, stride=1)
            for x_i in self.pyramid_layers
        })

        # smooth
        if self.is_pyramid:
            self.smooths = nn.ModuleDict()
            for pathway in self.pathways:
                smooths = nn.ModuleDict({
                    f'{pathway}_{x_i}': nn.Conv3d(self.planes, self.planes, kernel_size=3, stride=1, padding='same')
                    for x_i in self.pyramid_layers
                })
                self.smooths.update(smooths)
        else:
            self.smooths = None

        self.level_dict = {
            'x1': np.array([[1, 2, 4], [1, 2, 3], [1, 2, 3]]),
            'x2': np.array([[1, 2, 4], [1, 2, 3], [1, 2, 3]]),
            'x3': np.array([[1, 1, 2], [1, 2, 3], [1, 2, 3]]),
            'x4': np.array([[1, 1, 1], [1, 2, 3], [1, 2, 3]]),
        }
        self.pyramidpools = nn.ModuleDict({
            x_i: SpatialPyramidPooling(self.level_dict[x_i], hparams['pooling_mode'], hparams['softpool'])
            for x_i in self.pyramid_layers
        })

        self.fc_input_dims = {
            x_i: self.level_dict[x_i][0] * self.level_dict[x_i][1] * self.level_dict[x_i][2] * self.planes
            for x_i in self.pyramid_layers
        }

        if self.is_pyramid:
            self.fcs = nn.ModuleDict()
            for pathway in self.pathways:
                fcs = nn.ModuleDict({
                    f'{pathway}_{x_i}': nn.ModuleDict(
                        {f'level_{j}': build_fc(hparams, self.fc_input_dims[x_i][j], hparams['output_size'])
                         for j in range(len(self.level_dict[x_i][0]))})
                    for x_i in self.pyramid_layers
                })
                self.fcs.update(fcs)
        else:
            self.fcs = nn.ModuleDict({
                x_i: nn.ModuleDict({f'level_{j}': build_fc(hparams, self.fc_input_dims[x_i][j], hparams['output_size'])
                                    for j in range(len(self.level_dict[x_i][0]))})
                for x_i in self.pyramid_layers
            })

        if hparams.fc_fusion == 'concat':
            final_in_dim = hparams['layer_hidden'] * \
                           (len(self.pathways) if self.is_pyramid else 1) * \
                           len(self.pyramid_layers) * \
                           len(self.level_dict['x1'][0])
        elif hparams.fc_fusion == 'avg':
            final_in_dim = hparams['layer_hidden']
        elif hparams.fc_fusion == 'avgconcat':
            final_in_dim = hparams['layer_hidden'] * \
                           (len(self.pathways) if self.is_pyramid else 1) * \
                           len(self.pyramid_layers)

        self.final_fc = build_fc(hparams, final_in_dim, hparams['output_size'])

    def forward(self, x):

        # first conv
        x = dict(x[x_i] for x_i in self.pyramid_layers)
        x = {k: self.first_convs[k](v) for k, v in x.items()}

        if self.is_pyramid:
            x_all = {}
            if 'topdown' in self.pathways:
                x_topdown = self.pyramid_pathway(x, list(reversed(self.pyramid_layers)), 'topdown_')
                x_all.update(x_topdown)
            if 'bottomup' in self.pathways:
                x_bottomup = self.pyramid_pathway(x, self.pyramid_layers, 'bottomup_')
                x_all.update(x_bottomup)
            # 3x3 smooth
            x_all = {k: self.smooths[k](v) for k, v in x_all.items()}
            # pooling
            x_all = {k: self.pyramidpools[k.split('-')[-1]](v) for k, v in x_all.items()}
            x_aux, x_final = self.forward_fcs(x_all)

        else:  # one layer only (no smooth)
            x = {k: self.pyramidpools[k](v) for k, v in x.items()}
            x_aux, x_final = self.forward_fcs(x)

        return x_final, x_aux

    def pyramid_pathway(self, x, layers, prefix):
        x_new = {}
        for i, x_i in enumerate(layers):
            k = f'{prefix}{x_i}'
            if i == 0:
                x_new[k] = x[x_i].clone()
            else:
                x_new[k] = self.resample_and_add(prev, x[x_i].clone())
                x_new[k] = self.smooths[k](x_new[k])
            # x_new[k] = self.smooths[k](x_new[k]) #TODO: smooth for top layer?
            prev = x_new[k]
        return x_new

    def forward_fcs(self, x):
        x_inter_alls = {}
        for x_i in x.keys():
            k1 = f'{x_i}'
            x_inter_alls[k1] = {}
            for j in range(len(self.level_dict[x_i][0])):
                k2 = f'level_{j}'
                x[k1][k2] = self.fcs[k1][k2][:3](x[k1][k2])  # first layer
                x_inter_alls[k1][k2] = x[k1][k2].clone()
                x[k1][k2] = self.fcs[k1][k2][3:](x[k1][k2])  # aux head
        x_inter_alls = self.fusion(x_inter_alls, self.hparams.fc_fusion)
        x_final = self.final_fc(x_inter_alls)

        return x, x_final

    @staticmethod
    def fusion(x, type):
        if type == 'concat':
            x_all = torch.cat([v2 for k1, v1 in x.items() for k2, v2 in v1.items()], 1)
        elif type == 'avg':
            x_all = torch.stack([v2 for k1, v1 in x.items() for k2, v2 in v1.items()], -1)
            x_all = x_all.mean(-1)
        elif type == 'avgconcat':
            x_all = []
            for k1, v1 in x.items():
                x_tmp = []
                for k2, v2 in v1.items():
                    x_tmp.append(v2)
                x_tmp = torch.stack(x_tmp, -1)
                x_tmp = x_tmp.mean(-1)
                x_all.append(x_tmp)
            x_all = torch.cat(x_all, 1)
        else:
            NotImplementedError()

        return x_all

    @staticmethod
    def resample_and_add(x, y):
        target_shape = y.shape[2:]
        out = F.interpolate(x, size=target_shape, mode='nearest')
        return out + y


def modify_resnets(model):
    # Modify attributs
    model.last_linear, model.fc = model.fc, None

    def features(self, input):
        x = self.conv1(input)
        # print("conv, ", x.view(-1)[:10])
        x = self.bn1(x)
        x = self.relu(x)
        x = self.maxpool(x)  # torch.Size([1, 64, 8, 56, 56])

        x = self.layer1(x)  # torch.Size([1, 256, 8, 56, 56])
        x = self.layer2(x)  # torch.Size([1, 512, 4, 28, 28])
        x = self.layer3(x)  # torch.Size([1, 1024, 2, 14, 14])
        x = self.layer4(x)  # torch.Size([1, 2048, 1, 7, 7])
        return x

    def logits(self, features):
        x = self.avgpool(features)
        x = x.view(x.size(0), -1)
        x = self.last_linear(x)
        return x

    def forward(self, input):
        x = self.features(input)
        x = self.logits(x)
        return x

    # Modify methods
    setattr(model.__class__, 'features', features)
    setattr(model.__class__, 'logits', logits)
    setattr(model.__class__, 'forward', forward)
    return model


def modify_resnets_patrial_x3(model):
    del model.fc
    del model.last_linear
    del model.layer4

    def forward(self, x):
        x = self.conv1(x)
        x = self.bn1(x)
        x = self.relu(x)
        x = self.maxpool(x)
        x = self.layer1(x)
        x = self.layer2(x)
        x = self.layer3(x)
        return x

    setattr(model.__class__, 'forward', forward)
    return model


def modify_resnets_patrial_x4(model):
    del model.fc
    del model.last_linear

    def forward(self, x):
        x = self.conv1(x)
        x = self.bn1(x)
        x = self.relu(x)
        x = self.maxpool(x)
        x = self.layer1(x)
        x = self.layer2(x)
        x = self.layer3(x)
        x = self.layer4(x)
        return x

    setattr(model.__class__, 'forward', forward)
    return model


def modify_resnets_patrial_x2(model):
    del model.fc
    del model.last_linear
    del model.layer3
    del model.layer4

    def forward(self, x):
        x = self.conv1(x)
        x = self.bn1(x)
        x = self.relu(x)
        x = self.maxpool(x)
        x = self.layer1(x)
        x = self.layer2(x)
        return x

    setattr(model.__class__, 'forward', forward)
    return model


def modify_resnets_patrial_x_all(model):
    del model.fc
    del model.last_linear

    def forward(self, x):
        x = self.conv1(x)
        x = self.bn1(x)
        x = self.relu(x)
        x = self.maxpool(x)
        x1 = self.layer1(x)
        x2 = self.layer2(x1)
        x3 = self.layer3(x2)
        x4 = self.layer4(x3)
        return {
            'x1': x1,
            'x2': x2,
            'x3': x3,
            'x4': x4,
        }

    setattr(model.__class__, 'forward', forward)
    return model


ROOT_URL = 'http://moments.csail.mit.edu/moments_models'
weights = {
    'resnet50': 'moments_v2_RGB_resnet50_imagenetpretrained.pth.tar',
    'resnet3d50': 'moments_v2_RGB_imagenet_resnet3d50_segment16.pth.tar',
    'multi_resnet3d50': 'multi_moments_v2_RGB_imagenet_resnet3d50_segment16.pth.tar',
}


def load_checkpoint(weight_file):
    if not os.access(weight_file, os.W_OK):
        weight_url = os.path.join(ROOT_URL, weight_file)
        os.system('wget ' + weight_url)
    checkpoint = torch.load(weight_file, map_location=lambda storage, loc: storage)  # Load on cpu
    return {str.replace(str(k), 'module.', ''): v for k, v in checkpoint['state_dict'].items()}


def resnet50(num_classes=305, pretrained=True):
    model = models.__dict__['resnet50'](num_classes=num_classes)
    if pretrained:
        model.load_state_dict(load_checkpoint(weights['resnet50']))
    model = modify_resnets(model)
    return model


def resnet3d50(num_classes=305, pretrained=True, **kwargs):
    """Constructs a ResNet3D-50 model."""
    model = modify_resnets(ResNet3D(Bottleneck, [3, 4, 6, 3], num_classes=num_classes, **kwargs))
    if pretrained:
        model.load_state_dict(load_checkpoint(weights['resnet3d50']))
    return model


def multi_resnet3d50(num_classes=292, pretrained=True, cache_dir='~/.cache/', **kwargs):
    """Constructs a ResNet3D-50 model."""
    model = modify_resnets(ResNet3D(Bottleneck, [3, 4, 6, 3], num_classes=num_classes, **kwargs))
    if pretrained:
        model.load_state_dict(load_checkpoint(os.path.join(cache_dir, weights['multi_resnet3d50'])))
    return model


def load_model(arch):
    model = {'resnet3d50': resnet3d50,
             'multi_resnet3d50': multi_resnet3d50, 'resnet50': resnet50}.get(arch, 'resnet3d50')()
    model.eval()
    return model


def load_transform():
    """Load the image transformer."""
    return transforms.Compose([
        transforms.Resize((224, 224)),
        transforms.ToTensor(),
        transforms.Normalize([0.485, 0.456, 0.406],
                             [0.229, 0.224, 0.225])])


def load_categories(filename):
    """Load categories."""
    with open(filename) as f:
        return [line.rstrip() for line in f.readlines()]
