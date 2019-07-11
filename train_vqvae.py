import argparse

import torch
from torch import nn, optim
from torch.utils.data import DataLoader

from torchvision import datasets, transforms, utils

from tqdm import tqdm

from vqvae import VQVAE
from scheduler import CycleScheduler


def train(epoch, loader, model, optimizer, scheduler, device, loader_):
    loader = tqdm(loader)
    loader_ = tqdm(loader_)

    criterion = nn.MSELoss()

    latent_loss_weight = 0.25
    sample_size = 25

    mse_sum = 0
    mse_n = 0

    for i, (img, label) in enumerate(loader):
        model.zero_grad()

        img = img.to(device)

        out, latent_loss, id_t, _ = model(img)
        recon_loss = criterion(out, img)
        latent_loss = latent_loss.mean()
        loss = recon_loss + latent_loss_weight * latent_loss
        loss.backward()

        if scheduler is not None:
            scheduler.step()
        optimizer.step()

        mse_sum += recon_loss.item() * img.shape[0]
        mse_n += img.shape[0]

        lr = optimizer.param_groups[0]['lr']

        loader.set_description(
            (
                f'epoch: {epoch + 1}; mse: {recon_loss.item():.5f}; '
                f'latent: {latent_loss.item():.3f}; avg mse: {mse_sum / mse_n:.5f}; '
                f'lr: {lr:.5f}'
            )
        )

        if i % 100 == 0:
            model.eval()

            sample = img[:sample_size]
            # img_, _ = loader_.next()
            for _, (img_, label) in enumerate(loader_):
                img_ = img_.to(device)
                break
            sample_ = img_[:sample_size]
            with torch.no_grad():
                out, _, id_t, quant = model(sample)
                out_, _, id_t_ ,quant_ = model(sample_)
            
            #print(id_t.shape)
            #print(quant.shape)
            id_t = id_t.unsqueeze(1)
            id_t = id_t.repeat(1, 3, 8, 8)
            #quant = quant.unsqueeze(2)
            quant = quant.repeat(1, 1, 8, 8)

            id_t_ = id_t_.unsqueeze(1)
            id_t_ = id_t_.repeat(1, 3, 8, 8)
            # print(sample_.type)
            #id_b = (id_b - 256 )/2
            # print(sample_)
            # id_t /= 512
            id_t = (id_t -256 )/2
            utils.save_image(
                torch.cat([sample, out, quant.type(torch.float),  id_t.type(torch.float), sample_, out_, id_t_.type(torch.float) ], 0),
                f'sample/{str(epoch + 1).zfill(5)}_{str(i).zfill(5)}.png',
                nrow=sample_size,
                normalize=True,
                range=(-1, 1),
            )
   
            #      id_t[0:1,]/512,
            #      f'top/{str(epoch + 1).zfill(5)}_{str("test")}_{str(i).zfill(5)}.png',
            #      nrow=sample_size,
           #      normalize=True,
           #       range=(-1, 1),
           #   )
                

            # utils.save_image(
            #      id_b,
            #      f'bottom/{str(epoch + 1).zfill(5)}_{str("test")}_{str(i).zfill(5)}.png',
            #      nrow=sample_size,
            #      normalize=True,
            #      range=(-1, 1),
            #  )                

            model.train()



if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--size', type=int, default=256)
    parser.add_argument('--epoch', type=int, default=560)
    parser.add_argument('--lr', type=float, default=3e-4)
    parser.add_argument('--sched', type=str)
    parser.add_argument('--path1', type=str)
    parser.add_argument('--path2', type=str)
    args = parser.parse_args()

    print(args)

    device = 'cuda'

    transform = transforms.Compose(
        [
            transforms.Resize(args.size),
            transforms.CenterCrop(args.size),
            transforms.ToTensor(),
            transforms.Normalize([0.5, 0.5, 0.5], [0.5, 0.5, 0.5]),
        ]
    )

    dataset = datasets.ImageFolder(args.path1, transform=transform)
    loader = DataLoader(dataset, batch_size=128, shuffle=True, num_workers=4)
    
    dataset_ = datasets.ImageFolder(args.path2, transform=transform)
    loader_ = DataLoader(dataset_, batch_size=128, shuffle=True, num_workers=4)
    
    model = nn.DataParallel(VQVAE()).to(device)

    optimizer = optim.Adam(model.parameters(), lr=args.lr)
    scheduler = None
    if args.sched == 'cycle':
        scheduler = CycleScheduler(
            optimizer, args.lr, n_iter=len(loader) * args.epoch, momentum=None
        )

    for i in range(args.epoch):
        train(i, loader, model, optimizer, scheduler, device, loader_)
        torch.save(
            model.module.state_dict(), f'checkpoint/vqvae_{str(i + 1).zfill(3)}.pt'
        )
