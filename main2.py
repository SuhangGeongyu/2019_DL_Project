import dataset
from tqdm import tqdm 
import torch 
import copy
import time
from torch import nn 
from torch.autograd import Variable
from torch.utils import data as da 
from torch.utils.data.sampler import SubsetRandomSampler
import torchvision.transforms as transforms
from torchvision.datasets import voc
import os 
import argparse
from optimizers import RAdam
from torchsummary import summary
import torchvision 
import torch.backends.cudnn as cudnn
from unet import Unet2D
from utils import optimize_linear
from losses import DiceLoss, SmoothCrossEntropyLoss
from medpy.metric import binary
import numpy as np
from sklearn.metrics import accuracy_score

parser = argparse.ArgumentParser()
parser.add_argument("--mode", default="segmentation", type=str, help="Task Type, For example segmentation or classification")
parser.add_argument("--optim", default="radam", type=str, help="Optimizers")
parser.add_argument("--loss-function", default="bce", type=str)
parser.add_argument("--epochs", default=50, type=int)
parser.add_argument('--method', default="adv", type=str)
parser.add_argument("--exp", default="Test", type=str)
parser.add_argument("--tricks", default="None", type=str)
args = parser.parse_args()

def train(model, trn_loader, criterion, optimizer, epoch, mode="classification"):
    trn_loss = 0
    start_time = time.time()
    sum_iou = 0 
    sum_acc = 0 
    for i, (image, target) in enumerate(trn_loader) :
        model.train()
        x = image.cuda()
        y = target.cuda()
        y_pred = model(x)
        import ipdb; ipdb.set_trace()
        
        if mode == "segmentation" : 
            loss = criterion(y_pred, y.long())

        elif mode == "classification" :
            loss = criterion(y_pred, y)
                
        optimizer.zero_grad()
        loss.backward()
        optimizer.step()
                       
        trn_loss += (loss)
        end_time = time.time()
        print(" [Training] [{0}] [{1}/{2}] Losses = [{3:.4f}] Time(Seconds) = [{4:.2f}] Measure = [{4:.3f}]".format(epoch, i, len(trn_loader), loss.item(), end_time-start_time))
        start_time = time.time()

    trn_loss = trn_loss/len(trn_loader)

    if mode == "segmentation" : 
        pass
    elif mode == "classification" :
        pass

    if epoch == 24 or epoch == 49 or epoch == 74 or epoch == 99  or epoch == 124 or epoch == 149 or epoch == 174 or epoch == 199: 
        torch.save(model.state_dict(), '{0}{1}_{2}_{3}.pth'.format("./", 'model', epoch, args.exp))

    return trn_loss#, total_measure

def validate(model, val_loader, criterion, criterion_fn, optimizer, epoch, mode="segmentation"):
    val_loss = 0 
    model.eval()
    adv_losses = 0
    sum_iou = 0 
    adv_sum_iou = 0
    start_time = time.time()

    if args.method == 'adv' :
        for i, (data, target) in enumerate(val_loader) :
            x = data.cuda()
            y = target.cuda()
            x_clone = Variable(x.clone().detach(), requires_grad=True).cuda()
            model_fn = copy.deepcopy(model)
            loss_fn = criterion_fn(model_fn(x_clone), y.long())

            optimizer.zero_grad()
            loss_fn.backward()

            grads = x_clone.grad

            # calculate perturbations of the inputs
            scaled_perturbation = optimize_linear(grads, eps=0.25, norm=np.inf)
            # make adversarial samples
            adv_x = Variable(x_clone+scaled_perturbation, requires_grad=True).cuda()
            
            # put acv_x into the model
            adv_y_pred = model_fn(adv_x)

            if mode == "segmentation" : 
                adv_loss = criterion_fn(adv_y_pred, y.detach().long())

            elif mode == "classification" :
                adv_loss = criterion_fn(adv_y_pred, y)

            adv_losses += adv_loss.item()
            
            optimizer.zero_grad()

            end_time = time.time()
            print(" [Validation] [{0}] [{1}/{2}] Adv. Losses = [{3:.4f}] Time(Seconds) = [{4:.2f}] Measure [{4:.3f}]".format(epoch, i, len(val_loader), adv_loss.item(), end_time-start_time))
            start_time = time.time()
    else  :
        with torch.no_grad() :
            for i, (data, target) in enumerate(val_loader) :
                x = data.cuda()
                y = target.cuda()

                y_pred = model(x)

                if mode == "segmentation" : 
                    loss = criterion(y_pred, y.long())

                elif mode == "classification" :
                    loss = criterion(y_pred, y)
                val_loss += (loss)

                end_time = time.time()
                print(" [Validation] [{0}] [{1}/{2}] Losses = [{3:.4f}] Time(Seconds) = [{4:.2f}] Measure [{4:.3f}]".format(epoch, i, len(val_loader), loss.item(), end_time-start_time))
                start_time = time.time()

    
    if mode == "segmentation" : 
        pass
    elif mode == "classification" :
        pass

    if args.method != 'adv' :
        val_loss = val_loss / len(val_loader)
        return val_loss
    else : 
        adv_losses /= len(val_loader)
        return adv_losses


def draw_plot(real_photo, segmentationmap, predict_map) :
    import matplotlib.pyplot as plt 
    import seaborn as sns 
    #from PIL import Image 
    #palette = torch.tensor([2 ** 25 - 1, 2 ** 15 - 1, 2 ** 21 - 1])
    #colors = torch.as_tensor([i for i in range(21)])[:, None] * palette
    #colors = (colors % 255).numpy().astype("uint8")
    #r = Image.fromarray(y_pred[0].byte().cpu().numpy().astype("uint8").reshape(256, 256))
    #r.putpalette(colors)
    #r.save("test3.png") 
    
def main():
    if args.mode == "segmentation" :
        label_path = "seg_da/VOCdevkit/VOC2010/SegmentationClass/"
        image_path = "seg_da/VOCdevkit/VOC2010/JPEGImages"

        if args.tricks == "cut-off" :
            trainset = dataset.voc_seg(label_path, image_path, cut_out=True)
            valset = dataset.voc_seg(label_path, image_path, cut_out=False)
            total_idx = list(range(len(trainset)))
            split_idx = int(len(trainset) * 0.7)
            trn_idx = total_idx[:split_idx]
            val_idx = total_idx[split_idx:]
        elif args.tricks == "smoothing" :
            trainset = dataset.voc_seg(label_path, image_path, cut_out=False)
            valset = dataset.voc_seg(label_path, image_path, cut_out=False)
            total_idx = list(range(len(trainset)))
            split_idx = int(len(trainset) * 0.7)
            trn_idx = total_idx[:split_idx]
            val_idx = total_idx[split_idx:]
        elif args.tricks == "all" :
            trainset = dataset.voc_seg(label_path, image_path, cut_out=True)
            valset = dataset.voc_seg(label_path, image_path, cut_out=False)
            total_idx = list(range(len(trainset)))
            split_idx = int(len(trainset) * 0.7)
            trn_idx = total_idx[:split_idx]
            val_idx = total_idx[split_idx:]
        else :
            trainset = dataset.voc_seg(label_path, image_path, cut_out=False)
            total_idx = list(range(len(trainset)))
            split_idx = int(len(trainset) * 0.7)
            trn_idx = total_idx[:split_idx]
            val_idx = total_idx[split_idx:]

    elif args.mode == "classification" :
        info_path = "seg_da/VOCdevkit/VOC2010/SegmentationClass/"
        image_path = "seg_da/VOCdevkit/VOC2010/JPEGImages"

        if args.tricks == "smoothing" :
            trainset = dataset.voc_cls_smoothing(label_path, image_path)
            valset = dataset.voc_cls(label_path, image_path, cut_out=False)
            total_idx = list(range(len(trainset)))
            split_idx = int(len(trainset) * 0.7)
            trn_idx = total_idx[:split_idx]
            val_idx = total_idx[split_idx:]
        
        elif args.tricks == "cut-off" :
            trainset = dataset.voc_seg(label_path, image_path, cut_out=True)
            valset = dataset.voc_seg(label_path, image_path, cut_out=False)
            total_idx = list(range(len(trainset)))
            split_idx = int(len(trainset) * 0.7)
            trn_idx = total_idx[:split_idx]
            val_idx = total_idx[split_idx:]

        else :
            trainset = dataset.voc_cls(info_path, image_path)
            total_idx = list(range(len(trainset)))
            split_idx = int(len(trainset) * 0.7)
            trn_idx = total_idx[:split_idx]
            val_idx = total_idx[split_idx:]
    else : 
        raise NotImplementedError

    trainloader = torch.utils.data.DataLoader(trainset, batch_size=32, shuffle=False, sampler=SubsetRandomSampler(trn_idx))
    testloader = torch.utils.data.DataLoader(trainset, batch_size=16, shuffle=False, sampler=SubsetRandomSampler(val_idx))

    if args.mode == "segmentation" :
        net = Unet2D((3, 256, 256), 1, 0.1, num_classes=21)
    elif args.mode == "classification" :
        net = torchvision.models.resnet50(pretrained=False, num_classes=20)
    else : 
        raise NotImplementedError

    if args.optim == 'sgd' :
        optimizer = torch.optim.SGD(net.parameters(), lr=0.01, momentum=0.9)
    elif args.optim == 'adam' :
        optimizer = torch.optim.Adam(net.parameters(), lr=0.001)
    elif args.optim == 'radam' :
        optimizer = RAdam(net.parameters(), lr = 0.001)

    net = nn.DataParallel(net).cuda()
    cudnn.benchmark = True

    if args.loss_function == "bce" :
        criterion = nn.BCEWithLogitsLoss().cuda()
        criterion_fn = nn.BCEWithLogitsLoss().cuda()

    elif args.loss_function == "dice" :
        criterion = DiceLoss().cuda()
        criterion_fn = DiceLoss().cuda()

    elif args.loss_function == "cross_entropy" :
        criterion = nn.CrossEntropyLoss().cuda()
        criterion_fn = nn.CrossEntropyLoss().cuda()

    elif args.loss_function == "smoothing" :
        criterion = nn.BCEWithLogitsLoss().cuda()
        criterion_fn = nn.BCEWithLogitsLoss().cuda()
    else :
        raise NotImplementedError
    
    losses = []
    val_losses = []
    for epoch in range(args.epochs) : 
        tr = train(net, trainloader, criterion, optimizer, epoch, mode=args.mode)
        va = validate(net, testloader, criterion, criterion_fn, optimizer, epoch, mode=args.mode)
        losses.append(tr)
        val_losses.append(va)

    return losses, val_losses


if __name__ == '__main__':
    tr_loss, val_loss = main()
    try :
        torch.save(tr_loss, args.mode + args.method + str(args.epochs) + "Trainloss.pkl")
        torch.save(val_loss, args.mode + args.method + str(args.epochs) + "Validation.pkl")
    except : 
        import ipdb; ipdb.set_trace()
    
