import torch
import torch.nn as nn
from types import SimpleNamespace
import torchvision

from .layers.MobileNetv2 import MobileNetv2
from .layers.Resnet import ResNet



class Linear(nn.Module):
    def __init__(self, in_channel, out_channel, bias=True, norm=True):
        super(Linear, self).__init__()
        self.bias = bias
        self.norm = norm
        self.linear = nn.Linear(in_channel, out_channel, bias)
        nn.init.xavier_uniform_(self.linear.weight, gain=0.01)

    def forward(self, x):
        y = x.matmul(self.linear.weight.t()) # y = weight * x
        
        # normalization
        if self.norm:
            x_norm = torch.norm(x, dim=1, keepdim=True)
            y = y / x_norm

        if self.bias:
            y = y + self.linear.bias
        return y


class Res50_Mobilenetv2_RLE(nn.Module):
    def __init__(self, cfg = None):
        super(Res50_Mobilenetv2_RLE, self).__init__()
        self.cfg = cfg
        self.num_joints = 32
       
        ''' 
            Backbone for PoseNet (ResNet50)
        '''
        self.preact = ResNet(f"resnet50")

        # Imagenet pretrain model
        import torchvision.models as tm  # noqa: F401,F403
        x = tm.resnet50(weights=None)

        self.feature_channel = 2048

        model_state = self.preact.state_dict()
        state = {k: v for k, v in x.state_dict().items()
                 if k in self.preact.state_dict() and v.size() == self.preact.state_dict()[k].size()}
        model_state.update(state)
        self.preact.load_state_dict(model_state)
        out_channel = self.feature_channel
        
        self.avg_pool = nn.AdaptiveAvgPool2d(1)
        
        #self.fcs, out_channel = self._make_fc_layer()
        self.root_idx = 0
        
        # full connection layers for pose
        self.fc_coord = Linear(out_channel, self.num_joints * 3)
        self.fc_sigma = Linear(out_channel, self.num_joints * 3, norm=False)
        
        
        '''
            Backbone for RootNet (MobileNetv2)
        '''
        self.preact_root = MobileNetv2()
        x = torchvision.models.mobilenet_v2(weights=None).eval()
        model_state = self.preact_root.state_dict()
        state = {k: v for k, v in x.state_dict().items()
                 if k in self.preact_root.state_dict() and v.size() == self.preact_root.state_dict()[k].size()}
        model_state.update(state)
        self.preact_root.load_state_dict(model_state)
        out_channel_root = 1280

        self.avg_pool_root = nn.AdaptiveAvgPool2d(1)

        # full connection layers for pose
        self.fc_coord_root = Linear(out_channel + out_channel_root, 3)
        self.fc_sigma_root = Linear(out_channel + out_channel_root, 3, norm=False)




    def forward(self, x, k, labels=None):
        BATCH_SIZE = x.shape[0]

        '''
            SinglePose
        '''
        feat = self.preact(x)                              # features extracted: B * out_channel * H * W
        feat = self.avg_pool(feat).reshape(BATCH_SIZE, -1) # average pooling：B * out_channel * 1 * 1 --> batch_size * out_channel

        out_coord = self.fc_coord(feat).reshape(BATCH_SIZE, self.num_joints, 3)  # B * (3*num_joints) --> B * num_joints * 3
        out_sigma = self.fc_sigma(feat).reshape(BATCH_SIZE, self.num_joints, -1) # B * (3*num_joints) --> B * num_joints * 3
        # (B, N, 3)
        pred_jts = out_coord.reshape(BATCH_SIZE, self.num_joints, 3)  # can be regared as miu
        if not self.training:
            pred_jts[:, :, 2] = pred_jts[:, :, 2] - pred_jts[:, self.root_idx:self.root_idx + 1, 2]

        sigma = out_sigma.reshape(BATCH_SIZE, self.num_joints, -1).sigmoid() + 1e-9 # [0,1]
        scores = 1 - sigma
        scores = torch.mean(scores, dim=2, keepdim=True) # B * num_joints * 1

        
        '''
            DepthPose
        '''
        feat2 = self.preact_root(x)                                          # features extracted by mobilenetv2: B * out_channel * H * W
        feat2 = self.avg_pool_root(feat2).reshape(BATCH_SIZE, -1)            # average pooling：B * out_channel * 1 * 1 --> B * out_channel
        feat_root = torch.cat((feat, feat2), dim = 1)                        # B * (out_channel + out_channel_root)
        pred_root = self.fc_coord_root(feat_root).reshape(BATCH_SIZE, 1, 3)  # B * 3 --> B * 1 * 3
        sigma_root = self.fc_sigma_root(feat_root).reshape(BATCH_SIZE, 1, -1)# B * 3 --> B * 1 * 3
        sigma_root = sigma_root.reshape(BATCH_SIZE, 1, -1).sigmoid() + 1e-9  # [0,1]
        scores_root = 1 - sigma_root
        scores_root = torch.mean(scores_root, dim=2, keepdim=True) # B * 1 * 1
        
        pred_root[:, 0, 2] *= k.view(-1)


        output = SimpleNamespace(
            pred_jts=pred_jts,
            maxvals=scores.float(),
            pred_root=pred_root,
            maxvals_root=scores_root.float(),
        )
        
        return output


# model = Mobilenetv2_3D_RLE()
# print(sum(p.numel() for p in model.parameters()))
# for name, param in model.named_parameters():
#     if 'preact2' in name:
#         print(name, param.size())