#!/usr/bin/python
# -*- coding: UTF-8 -*-
import time

import math
from torch.utils import model_zoo
import torch
from torch.autograd import Variable
import numpy as np
import torch.nn as nn
import torch.nn.functional as F
from torch.autograd import Variable
from torchvision import models

from semseg.loss import cross_entropy2d

# webroot = 'https://tigress-web.princeton.edu/~fy/drn/models/'
#
# model_urls = {
#     'drn-c-26': webroot + 'drn_c_26-ddedf421.pth',
#     'drn-c-42': webroot + 'drn_c_42-9d336e8c.pth',
#     'drn-c-58': webroot + 'drn_c_58-0a53a92c.pth',
#     'drn-d-22': webroot + 'drn_d_22-4bd2f8ea.pth',
#     'drn-d-38': webroot + 'drn_d_38-eebb45f0.pth',
#     'drn-d-54': webroot + 'drn_d_54-0e0534ff.pth',
#     'drn-d-105': webroot + 'drn_d_105-12b40979.pth'
# }
from semseg.modelloader.utils import AlignedResInception
from semseg.pytorch_modelsize import SizeEstimator


class Inception(nn.Module):
    def __init__(self, in_planes, n1x1, n3x3red, n3x3, n5x5red, n5x5, pool_planes):
        super(Inception, self).__init__()
        # 1x1 conv branch
        self.b1 = nn.Sequential(
            nn.Conv2d(in_planes, n1x1, kernel_size=1),
            nn.BatchNorm2d(n1x1),
            nn.ReLU(True),
        )

        # 1x1 conv -> 3x3 conv branch
        self.b2 = nn.Sequential(
            nn.Conv2d(in_planes, n3x3red, kernel_size=1),
            nn.BatchNorm2d(n3x3red),
            nn.ReLU(True),
            nn.Conv2d(n3x3red, n3x3, kernel_size=3, padding=1),
            nn.BatchNorm2d(n3x3),
            nn.ReLU(True),
        )

        # 1x1 conv -> 5x5 conv branch
        self.b3 = nn.Sequential(
            nn.Conv2d(in_planes, n5x5red, kernel_size=1),
            nn.BatchNorm2d(n5x5red),
            nn.ReLU(True),
            nn.Conv2d(n5x5red, n5x5, kernel_size=3, padding=1),
            nn.BatchNorm2d(n5x5),
            nn.ReLU(True),
            nn.Conv2d(n5x5, n5x5, kernel_size=3, padding=1),
            nn.BatchNorm2d(n5x5),
            nn.ReLU(True),
        )

        # 3x3 pool -> 1x1 conv branch
        self.b4 = nn.Sequential(
            nn.MaxPool2d(3, stride=1, padding=1),
            nn.Conv2d(in_planes, pool_planes, kernel_size=1),
            nn.BatchNorm2d(pool_planes),
            nn.ReLU(True),
        )

    def forward(self, x):
        y1 = self.b1(x)
        y2 = self.b2(x)
        y3 = self.b3(x)
        y4 = self.b4(x)
        return torch.cat([y1,y2,y3,y4], 1)

class ResInception(nn.Module):
    def __init__(self, in_planes, n1x1, n3x3red, n3x3, n5x5red, n5x5, pool_planes, stride=1):
        super(ResInception, self).__init__()
        self.relu = nn.ReLU(inplace=True)
        # 1x1 conv branch
        self.b1 = nn.Sequential(
            nn.Conv2d(in_planes, n1x1, kernel_size=1, stride=stride),
            nn.BatchNorm2d(n1x1),
            nn.ReLU(True),
        )

        # 1x1 conv -> 3x3 conv branch
        self.b2 = nn.Sequential(
            nn.Conv2d(in_planes, n3x3red, kernel_size=1, stride=stride),
            nn.BatchNorm2d(n3x3red),
            nn.ReLU(True),
            nn.Conv2d(n3x3red, n3x3, kernel_size=3, padding=1),
            nn.BatchNorm2d(n3x3),
            nn.ReLU(True),
        )

        # 1x1 conv -> 5x5 conv branch
        self.b3 = nn.Sequential(
            nn.Conv2d(in_planes, n5x5red, kernel_size=1, stride=stride),
            nn.BatchNorm2d(n5x5red),
            nn.ReLU(True),
            nn.Conv2d(n5x5red, n5x5, kernel_size=3, padding=1),
            nn.BatchNorm2d(n5x5),
            nn.ReLU(True),
            nn.Conv2d(n5x5, n5x5, kernel_size=3, padding=1),
            nn.BatchNorm2d(n5x5),
            nn.ReLU(True),
        )

        # 3x3 pool -> 1x1 conv branch
        self.b4 = nn.Sequential(
            nn.MaxPool2d(3, stride=stride, padding=1),
            nn.Conv2d(in_planes, pool_planes, kernel_size=1),
            nn.BatchNorm2d(pool_planes),
            nn.ReLU(True),
        )

        self.downsample = None
        if stride>1:
            self.downsample = nn.Sequential(
                nn.Conv2d(in_planes, in_planes, kernel_size=1, stride=stride, bias=False),
                nn.BatchNorm2d(in_planes),
            )

    def forward(self, x):
        y1 = self.b1(x)
        y2 = self.b2(x)
        y3 = self.b3(x)
        y4 = self.b4(x)
        out = torch.cat([y1,y2,y3,y4], 1)
        if self.downsample is not None:
            out = out + self.downsample(x)
        else:
            out = out + x
        out = self.relu(out)
        return out


class CascadeResInception(nn.Module):
    def __init__(self):
        super(CascadeResInception, self).__init__()
        self.relu = nn.ReLU(inplace=True)
        self.res1 = ResInception(512, 128, 128, 256, 24,  64,  64, stride=2)
        self.res2 = ResInception(512, 128, 128, 256, 24,  64,  64, stride=7)
        self.res3 = ResInception(512, 128, 128, 256, 24,  64,  64, stride=14)

    def forward(self, x):
        y1 = self.res1(x)
        y2 = self.res2(x)
        y3 = self.res3(x)
        # print('y1:', y1.size())
        # print('y2:', y2.size())
        # print('y3:', y3.size())
        y1 = F.upsample_bilinear(y1, x.size()[2:])
        y2 = F.upsample_bilinear(y2, x.size()[2:])
        y3 = F.upsample_bilinear(y3, x.size()[2:])
        out = x + y1 + y2 + y3
        out = self.relu(out)
        return out

class CascadeAlignedResInception(nn.Module):
    def __init__(self, in_planes):
        super(CascadeAlignedResInception, self).__init__()
        self.relu = nn.ReLU(inplace=True)
        self.res1 = AlignedResInception(in_planes=in_planes, stride=2)
        self.res2 = AlignedResInception(in_planes=in_planes, stride=7)
        self.res3 = AlignedResInception(in_planes=in_planes, stride=14)

    def forward(self, x):
        y1 = self.res1(x)
        y2 = self.res2(x)
        y3 = self.res3(x)
        # print('y1:', y1.size())
        # print('y2:', y2.size())
        # print('y3:', y3.size())
        y1 = F.upsample_bilinear(y1, x.size()[2:])
        y2 = F.upsample_bilinear(y2, x.size()[2:])
        y3 = F.upsample_bilinear(y3, x.size()[2:])
        out = x + y1 + y2 + y3
        out = self.relu(out)
        return out

def conv3x3(in_planes, out_planes, stride=1, padding=1, dilation=1):
    return nn.Conv2d(in_planes, out_planes, kernel_size=3, stride=stride,
                     padding=padding, bias=False, dilation=dilation)

# drn基本构成块
class BasicBlock(nn.Module):
    expansion = 1

    def __init__(self, inplanes, planes, stride=1, downsample=None,
                 dilation=(1, 1), residual=True):
        super(BasicBlock, self).__init__()
        # dilation默认为(1,1)由两个dilation的卷积模块构成，由于stride=1，dilation为1，kernel为3
        # 那么相当于kernel为6的卷积核，padding为1
        self.conv1 = conv3x3(inplanes, planes, stride,
                             padding=dilation[0], dilation=dilation[0])
        self.bn1 = nn.BatchNorm2d(planes)
        self.relu = nn.ReLU(inplace=True)
        self.conv2 = conv3x3(planes, planes,
                             padding=dilation[1], dilation=dilation[1])
        self.bn2 = nn.BatchNorm2d(planes)
        self.downsample = downsample
        self.stride = stride
        self.residual = residual

    def forward(self, x):
        residual = x

        # print(x.data.size())
        out = self.conv1(x)
        # print(out.data.size())
        out = self.bn1(out)
        out = self.relu(out)

        out = self.conv2(out)
        out = self.bn2(out)

        if self.downsample is not None:
            residual = self.downsample(x)
        if self.residual:
            out += residual
        out = self.relu(out)

        return out

class Bottleneck(nn.Module):
    expansion = 4

    def __init__(self, inplanes, planes, stride=1, downsample=None, dilation=(1, 1), residual=True):
        super(Bottleneck, self).__init__()
        self.conv1 = nn.Conv2d(inplanes, planes, kernel_size=1, bias=False)
        self.bn1 = nn.BatchNorm2d(planes)
        self.conv2 = nn.Conv2d(planes, planes, kernel_size=3, stride=stride,
                               padding=dilation[1], bias=False,
                               dilation=dilation[1])
        self.bn2 = nn.BatchNorm2d(planes)
        self.conv3 = nn.Conv2d(planes, planes * 4, kernel_size=1, bias=False)
        self.bn3 = nn.BatchNorm2d(planes * 4)
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

class DRN(nn.Module):

    def __init__(self, block, layers, num_classes=1000, channels=(16, 32, 64, 128, 256, 512, 512, 512), out_map=False, out_middle=False, pool_size=28, arch='D'):
        super(DRN, self).__init__()
        print(layers)
        self.inplanes = channels[0]
        self.out_map = out_map
        self.out_dim = channels[-1]
        self.out_middle = out_middle
        # 默认架构为arch=D
        self.arch = arch

        # 不同架构主要在构成的网络模块基本组成模块上不同，在C架构上主要由basic block块组成，而其他由conv组成
        if arch == 'C':
            self.conv1 = nn.Conv2d(3, channels[0], kernel_size=7, stride=1, padding=3, bias=False)
            self.bn1 = nn.BatchNorm2d(channels[0])
            self.relu = nn.ReLU(inplace=True)

            self.layer1 = self._make_layer(BasicBlock, channels[0], layers[0], stride=1)
            self.layer2 = self._make_layer(BasicBlock, channels[1], layers[1], stride=2)
        elif arch == 'D' or arch == 'E':
            # -7+2*3/1+1=0将channel为3的rgb原始图像数据转换为channels[0]的数据
            self.layer0 = nn.Sequential(
                nn.Conv2d(3, channels[0], kernel_size=7, stride=1, padding=3, bias=False),
                nn.BatchNorm2d(channels[0]),
                nn.ReLU(inplace=True)
            )

            self.layer1 = self._make_conv_layers(channels[0], layers[0], stride=1)
            self.layer2 = self._make_conv_layers(channels[1], layers[1], stride=2)

        self.layer3 = self._make_layer(block, channels[2], layers[2], stride=2)
        self.layer4 = self._make_layer(block, channels[3], layers[3], stride=2)
        self.layer5 = self._make_layer(block, channels[4], layers[4], dilation=2, new_level=False)
        self.layer6 = None if layers[5] == 0 else self._make_layer(block, channels[5], layers[5], dilation=4, new_level=False)

        if arch == 'C':
            self.layer7 = None if layers[6] == 0 else self._make_layer(BasicBlock, channels[6], layers[6], dilation=2, new_level=False, residual=False)
            self.layer8 = None if layers[7] == 0 else self._make_layer(BasicBlock, channels[7], layers[7], dilation=1, new_level=False, residual=False)
        elif arch == 'D' or arch == 'E':
            # 无残差模块
            self.layer7 = None if layers[6] == 0 else self._make_conv_layers(channels[6], layers[6], dilation=2)
            self.layer8 = None if layers[7] == 0 else self._make_conv_layers(channels[7], layers[7], dilation=1)

        self.layer9 = None
        if arch == 'E':
            # self.layer9 = Inception(512, 128, 128, 256, 24,  64,  64)
            # self.layer9 = ResInception(512, 128, 128, 256, 24,  64,  64)
            # self.layer9 = CascadeResInception()
            # self.layer9 = CascadeAlignedResInception(in_planes=512)
            self.layer9 = AlignedResInception(in_planes=512)

        # 最后的网络输出语义图
        if num_classes > 0:
            self.avgpool = nn.AvgPool2d(pool_size)
            self.fc = nn.Conv2d(self.out_dim, num_classes, kernel_size=1, stride=1, padding=0, bias=True)

        # 网络模块权重和偏置初始化
        for m in self.modules():
            if isinstance(m, nn.Conv2d):
                n = m.kernel_size[0] * m.kernel_size[1] * m.out_channels
                m.weight.data.normal_(0, math.sqrt(2. / n))
            elif isinstance(m, nn.BatchNorm2d):
                m.weight.data.fill_(1)
                m.bias.data.zero_()

    # 这种构成网络层的方法类似于Residual Neural Network
    def _make_layer(self, block, planes, blocks, stride=1, dilation=1, new_level=True, residual=True):
        assert dilation == 1 or dilation % 2 == 0
        downsample = None
        if stride != 1 or self.inplanes != planes * block.expansion:
            downsample = nn.Sequential(
                nn.Conv2d(self.inplanes, planes * block.expansion,
                          kernel_size=1, stride=stride, bias=False),
                nn.BatchNorm2d(planes * block.expansion),
            )

        layers = list()
        layers.append(
            block(self.inplanes, planes, stride, downsample,
            dilation=(1, 1) if dilation == 1 else (dilation // 2 if new_level else dilation, dilation),
            residual=residual
            )
        )
        self.inplanes = planes * block.expansion
        for i in range(1, blocks):
            layers.append(block(self.inplanes, planes, residual=residual, dilation=(dilation, dilation)))

        return nn.Sequential(*layers)

    # 创建卷积层，输入通道，卷积个数，stride，dilation等等
    def _make_conv_layers(self, channels, convs, stride=1, dilation=1):
        modules = []
        # 创建卷积的个数，当stride为2时，即卷积有两层的情况下，输出维度为原来的1／2
        for i in range(convs):
            modules.extend([
                nn.Conv2d(self.inplanes, channels, kernel_size=3, stride=stride if i == 0 else 1, padding=dilation, bias=False, dilation=dilation),
                nn.BatchNorm2d(channels),
                nn.ReLU(inplace=True)])
            self.inplanes = channels
        return nn.Sequential(*modules)

    def forward(self, x):
        y = list()

        if self.arch == 'C':
            x = self.conv1(x)
            x = self.bn1(x)
            x = self.relu(x)
        elif self.arch == 'D' or self.arch == 'E':
            x = self.layer0(x)

        x = self.layer1(x)
        y.append(x)
        x = self.layer2(x)
        y.append(x)

        x = self.layer3(x)
        y.append(x)

        x = self.layer4(x)
        y.append(x)

        x = self.layer5(x)
        y.append(x)

        if self.layer6 is not None:
            x = self.layer6(x)
            y.append(x)

        if self.layer7 is not None:
            x = self.layer7(x)
            y.append(x)

        if self.layer8 is not None:
            x = self.layer8(x)
            y.append(x)

        # DRN E
        if self.layer9 is not None:
            x = self.layer9(x)
            y.append(x)

        if self.out_map:
            x = self.fc(x)
        else:
            x = self.avgpool(x)
            x = self.fc(x)
            x = x.view(x.size(0), -1)

        if self.out_middle:
            return x, y
        else:
            return x

class DRN_A(nn.Module):

    def __init__(self, block, layers, num_classes=1000):
        self.inplanes = 64
        super(DRN_A, self).__init__()
        self.out_dim = 512 * block.expansion
        self.conv1 = nn.Conv2d(3, 64, kernel_size=7, stride=2, padding=3, bias=False)
        self.bn1 = nn.BatchNorm2d(64)
        self.relu = nn.ReLU(inplace=True)
        self.maxpool = nn.MaxPool2d(kernel_size=3, stride=2, padding=1)
        self.layer1 = self._make_layer(block, 64, layers[0])
        self.layer2 = self._make_layer(block, 128, layers[1], stride=2)
        self.layer3 = self._make_layer(block, 256, layers[2], stride=1, dilation=2)
        self.layer4 = self._make_layer(block, 512, layers[3], stride=1, dilation=4)
        self.avgpool = nn.AvgPool2d(28, stride=1)
        self.fc = nn.Linear(512 * block.expansion, num_classes)

        for m in self.modules():
            if isinstance(m, nn.Conv2d):
                n = m.kernel_size[0] * m.kernel_size[1] * m.out_channels
                m.weight.data.normal_(0, math.sqrt(2. / n))
            elif isinstance(m, nn.BatchNorm2d):
                m.weight.data.fill_(1)
                m.bias.data.zero_()

        # for m in self.modules():
        #     if isinstance(m, nn.Conv2d):
        #         nn.init.kaiming_normal_(m.weight, mode='fan_out', nonlinearity='relu')
        #     elif isinstance(m, nn.BatchNorm2d):
        #         nn.init.constant_(m.weight, 1)
        #         nn.init.constant_(m.bias, 0)

    def _make_layer(self, block, planes, blocks, stride=1, dilation=1):
        downsample = None
        if stride != 1 or self.inplanes != planes * block.expansion:
            downsample = nn.Sequential(
                nn.Conv2d(self.inplanes, planes * block.expansion,
                          kernel_size=1, stride=stride, bias=False),
                nn.BatchNorm2d(planes * block.expansion),
            )

        layers = []
        layers.append(block(self.inplanes, planes, stride, downsample))
        self.inplanes = planes * block.expansion
        for i in range(1, blocks):
            layers.append(block(self.inplanes, planes,
                                dilation=(dilation, dilation)))

        return nn.Sequential(*layers)

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

def drn_a_50(pretrained=False, **kwargs):
    model = DRN_A(Bottleneck, [3, 4, 6, 3], **kwargs)
    if pretrained:
        model.load_state_dict(model_zoo.load_url('https://s3.amazonaws.com/pytorch/models/resnet50-19c8e357.pth'))
    return model

def drn_a_18(pretrained=False, **kwargs):
    model = DRN_A(BasicBlock, [2, 2, 2, 2], **kwargs)
    if pretrained:
        model.load_state_dict(model_zoo.load_url('https://s3.amazonaws.com/pytorch/models/resnet18-5c106cde.pth'))
    return model

# drn变种22
def drn_d_22(pretrained=False, **kwargs):
    model = DRN(BasicBlock, [1, 1, 2, 2, 2, 2, 1, 1], arch='D', **kwargs)
    # if pretrained:
    #     model.load_state_dict(model_zoo.load_url(model_urls['drn-d-22']))
    return model

# drn变种22
def drn_e_22(pretrained=False, **kwargs):
    model = DRN(BasicBlock, [1, 1, 2, 2, 2, 2, 1, 1], arch='E', **kwargs)
    # if pretrained:
    #     model.load_state_dict(model_zoo.load_url(model_urls['drn-d-22']))
    return model

# 转置卷积权重初始化填充方法
def fill_up_weights(up):
    w = up.weight.data
    f = math.ceil(w.size(2) / 2)
    c = (2 * f - 1 - f % 2) / (2. * f)
    for i in range(w.size(2)):
        for j in range(w.size(3)):
            w[0, 0, i, j] = (1 - math.fabs(i / f - c)) * (1 - math.fabs(j / f - c))
    for c in range(1, w.size(0)):
        w[c, 0, :, :] = w[0, 0, :, :]

# drn segnet network
class DRNSeg(nn.Module):
    def __init__(self, model_name, n_classes, pretrained=False, use_torch_up=False):
        super(DRNSeg, self).__init__()
        # DRN分割模型不同变种
        if model_name=='drn_d_22':
            model = drn_d_22(pretrained=pretrained, num_classes=1000)
        if model_name=='drn_a_50':
            model = drn_a_50(pretrained=pretrained, num_classes=1000)
        if model_name=='drn_a_18':
            model = drn_a_18(pretrained=pretrained, num_classes=1000)
        if model_name=='drn_e_22':
            model = drn_e_22(pretrained=pretrained, num_classes=1000)
        # pmodel = nn.DataParallel(model)
        # if pretrained_model is not None:
            # pmodel.load_state_dict(pretrained_model)
        self.base = nn.Sequential(*list(model.children())[:-2])

        # 仅仅在最后一层seg layer上存有bias
        self.seg = nn.Conv2d(model.out_dim, n_classes, kernel_size=1)
        # self.softmax = nn.LogSoftmax()
        m = self.seg

        # 初始化分割图最后的卷积weights和bias
        n = m.kernel_size[0] * m.kernel_size[1] * m.out_channels
        m.weight.data.normal_(0, math.sqrt(2. / n))
        m.bias.data.zero_()

        if use_torch_up:
            # 使用pytorch双向性上采样
            self.up = nn.UpsamplingBilinear2d(scale_factor=8)
        else:
            # 使用转置卷积上采样
            up = nn.ConvTranspose2d(n_classes, n_classes, 16, stride=8, padding=4, output_padding=0, groups=n_classes, bias=False)
            fill_up_weights(up)
            up.weight.requires_grad = False
            self.up = up

    def forward(self, x):
        x = self.base(x)

        # 将分割图对应到分割类别数上
        x = self.seg(x)

        # 使用双线性上采样或者转置卷积上采样8倍降采样率的分割图
        y = self.up(x)
        return y

    def optim_parameters(self, memo=None):
        for param in self.base.parameters():
            yield param
        for param in self.seg.parameters():
            yield param

if __name__ == '__main__':
    n_classes = 21
    model = DRNSeg(model_name='drn_d_22', n_classes=n_classes, pretrained=False)
    # model.eval()
    # model.init_vgg16()
    x = Variable(torch.randn(1, 3, 360, 480))
    y = Variable(torch.LongTensor(np.ones((1, 360, 480), dtype=np.int)))
    # x = Variable(torch.randn(1, 3, 512, 1024))
    # y = Variable(torch.LongTensor(np.ones((1, 512, 1024), dtype=np.int)))
    # print(x.shape)
    start = time.time()
    pred = model(x)
    end = time.time()
    print(end-start)
    # print(pred.shape)
    loss = cross_entropy2d(pred, y)
    print(loss)

    # se = SizeEstimator(model, input_size=(1, 3, 360, 480))
    # print(se.estimate_size())
