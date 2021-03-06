import os

import numpy as np

import torch
import torch.nn as nn
import torch.nn.functional as F
from torchvision import transforms

from model_i3d import build_fc, ConvResponseModel
from pyramidpooling3d import SpatialPyramidPooling3D, SpatialPyramidPooling2D


class BDCNNeck(nn.Module):
    def __init__(self, hparams):
        super(BDCNNeck, self).__init__()
        self.hparams = hparams
        assert self.hparams.separate_rois == False
        self.rois = self.hparams.rois

        self.pool_size = self.hparams.pooling_size

        self.is_lstm = True if self.hparams.lstm_layers > 0 else False

        if self.hparams.spp:
            levels = np.array(hparams['spp_size'])
            pool = SpatialPyramidPooling2D(
                levels=levels,
                mode=hparams['pooling_mode']
            )
            in_dim = np.sum(levels ** 2) * 1
        else:
            if self.hparams.pooling_mode == 'max':
                # pool = nn.MaxPool2d(kernel_size=self.pool_size, stride=self.pool_size)
                pool = nn.AdaptiveMaxPool2d(self.pool_size)
            elif self.hparams.pooling_mode == 'avg':
                # pool = nn.AvgPool2d(kernel_size=self.pool_size, stride=self.pool_size)
                pool = nn.AdaptiveAvgPool2d(self.pool_size)
            else:
                NotImplementedError()
            in_dim = int(self.pool_size ** 2 * 1)

        self.read_out_layers = nn.Sequential(
            nn.Sigmoid(),
            pool,
        )

        if self.is_lstm:
            self.lstm = nn.LSTM(input_size=in_dim, hidden_size=self.hparams.layer_hidden,
                                num_layers=self.hparams.lstm_layers, batch_first=True)
            if self.hparams['track'] == 'full_track':
                if self.hparams['no_convtrans']:
                    self.head = build_fc(hparams, self.hparams.layer_hidden * self.hparams.video_frames,
                                         hparams['output_size'])
                else:
                    self.head = ConvResponseModel(self.hparams.layer_hidden * self.hparams.video_frames,
                                                  hparams['num_subs'], hparams)
            else:
                self.head = build_fc(hparams, self.hparams.layer_hidden * self.hparams.video_frames,
                                   hparams['output_size'])
        else:
            if self.hparams['track'] == 'full_track':
                if self.hparams['no_convtrans']:
                    self.head = build_fc(hparams, in_dim,
                                         hparams['output_size'])
                else:
                    self.head = ConvResponseModel(in_dim,
                                                  hparams['num_subs'], hparams)
            else:
                self.head = build_fc(hparams, in_dim,
                                   hparams['output_size'])
    def forward(self, x):
        # x: (None, D, H, W)
        x = self.read_out_layers(x)
        # print(x.shape) torch.Size([24, 4, 16, 16])
        x = x.reshape(x.shape[0], x.shape[1], -1)
        if self.is_lstm:
            x = self.lstm(x)[0]
            out = self.head(x.reshape(x.shape[0], -1))
        else:
            s = x.shape
            # x = x.reshape(s[0]*s[1], -1)
            x = self.head(x)
            # x = x.reshape(s[0], s[1], *(x.shape[1:]))
            print(x.shape)
            out = x.mean(1) # baseline methods
        out_aux = None
        out = {self.rois: out}
        return out, out_aux
