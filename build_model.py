#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Copyright (c) 2020 by Inria
Authoried by Xiaoyu BIE (xiaoyu.bie@inrai.fr)
License agreement in LICENSE.txt
"""

import sys
import os
import socket
import datetime
import torch
from torch.utils import data

import librosa
from configparser import ConfigParser
from logger import get_logger
from model_vae import VAE
from model_rvae import RVAE


from backup_simon.speech_dataset import *



# Re-write configure class, enable to distinguish betwwen upper and lower letters
class myconf(ConfigParser):
    def __init__(self,defaults=None):
        ConfigParser.__init__(self,defaults=None)
    def optionxform(self, optionstr):
        return optionstr


class BuildBasic():

    """
    Basical class for model building, including:
    - read common paramters for different models
    - define data loader
    - define loss function as a class member
    """

    def __init__(self, cfg = myconf()):

        # Load config parser
        self.cfg = cfg
        self.model_name = self.cfg.get('Network', 'name')
        self.dataset_name = self.cfg.get('DataFrame', 'dataset_name')

        # Get host name and date
        self.hostname = socket.gethostname()
        self.date = datetime.datetime.now().strftime("%Y-%m-%d-%Hh%M")

        # Get logger type
        self.logger_type = self.cfg.getint('User', 'logger_type')

        # Load STFT parameters
        self.wlen_sec = self.cfg.getfloat('STFT', 'wlen_sec')
        self.hop_percent = self.cfg.getfloat('STFT', 'hop_percent')
        self.fs = self.cfg.getint('STFT', 'fs')
        self.zp_percent = self.cfg.getint('STFT', 'zp_percent')
        self.trim = self.cfg.getboolean('STFT', 'trim')
        self.verbose = self.cfg.getboolean('STFT', 'verbose')

        # Load training parameters
        self.lr = self.cfg.getfloat('Training', 'lr')
        self.epochs = self.cfg.getint('Training', 'epochs')
        self.batch_size = self.cfg.getint('Training', 'batch_size')
        self.optimization  = self.cfg.get('Training', 'optimization')
        self.early_stop_patience = self.cfg.getint('Training', 'early_stop_patience')
        self.save_frequency = self.cfg.getint('Training', 'save_frequency')

        # Create saved_model directory if not exist
        self.local_hostname = self.cfg.get('User', 'local_hostname')
        if self.hostname == self.local_hostname:
            self.path_prefix = self.cfg.get('Path', 'path_local')
        # ===== develop on Mac, temporarily =====
        elif self.hostname == 'MacPro-BIE.local': 
            self.path_prefix = self.cfg.get('Path', 'path_mac')
        # ===== develop on Mac, temporarily =====
        else: 
            self.path_prefix = self.cfg.get('Path', 'path_cluster')
        if not(os.path.isdir(self.path_prefix)):
            os.makedirs(self.path_prefix)

        # Choose to use gpu or cpu
        self.device = 'cuda' if torch.cuda.is_available() else 'cpu'

        # Define loss function
        def loss_function(recon_x, x, mu, logvar):
            recon = torch.sum(  x/recon_x - torch.log(x/recon_x) - 1 ) 
            KLD = -0.5 * torch.sum(logvar - mu.pow(2) - logvar.exp())
            return recon + KLD
        self.loss_function = loss_function

        # Define dataloader type
        self.get_seq = False

    def build_dataloader(self):
        # Find data set
        #train_data_dir, val_data_dir = find_dataset()
        self.train_data_dir = self.cfg.get('Path', 'train_data_dir')
        self.val_data_dir = self.cfg.get('Path', 'val_data_dir')
        # List all the data with certain suffix
        self.data_suffix = self.cfg.get('DataFrame', 'suffix')
        self.train_file_list = librosa.util.find_files(self.train_data_dir, ext=self.data_suffix)
        self.val_file_list = librosa.util.find_files(self.val_data_dir, ext=self.data_suffix)
        # Generate dataloader for pytorch
        self.num_workers = self.cfg.getint('DataFrame', 'num_workers')
        self.shuffle_file_list = self.cfg.get('DataFrame', 'shuffle_file_list')
        self.shuffle_samples_in_batch = self.cfg.get('DataFrame', 'shuffle_samples_in_batch')

        # Instranciate training dataloader
        if not self.get_seq:
            train_dataset = SpeechDatasetFrames(file_list = self.train_file_list,
                                                wlen_sec = self.wlen_sec,
                                                hop_percent = self.hop_percent,
                                                fs = self.fs,
                                                zp_percent = self.zp_percent,
                                                trim = self.trim,
                                                verbose = self.verbose,
                                                batch_size = self.batch_size,
                                                shuffle_file_list = self.shuffle_file_list,
                                                name = self.dataset_name)
        else:
            self.sequence_len = self.cfg.getint('DataFrame','sequence_len')
            train_dataset = SpeechDatasetSequences(file_list=self.train_file_list,
                                                   sequence_len=self.sequence_len,
                                                   wlen_sec=self.wlen_sec,
                                                   hop_percent=self.hop_percent,
                                                   fs=self.fs,
                                                   zp_percent=self.zp_percent,
                                                   trim=self.trim,
                                                   verbose=self.verbose,
                                                   batch_size=self.batch_size,
                                                   shuffle_file_list=self.shuffle_file_list,
                                                   name=self.dataset_name)
        train_num = train_dataset.num_samples

        # Instanciate validation dataloader
        if not self.get_seq:
            val_dataset = SpeechDatasetFrames(file_list = self.val_file_list,
                                              wlen_sec = self.wlen_sec,
                                              hop_percent = self.hop_percent,
                                              fs = self.fs,
                                              zp_percent = self.zp_percent,
                                              trim = self.trim,
                                              verbose = self.verbose,
                                              batch_size = self.batch_size,
                                              shuffle_file_list = self.shuffle_file_list,
                                              name = self.dataset_name)
        else:
            self.sequence_len = self.cfg.getint('DataFrame','sequence_len')
            val_dataset = SpeechDatasetSequences(file_list=self.val_file_list,
                                                 sequence_len=self.sequence_len,
                                                 wlen_sec=self.wlen_sec,
                                                 hop_percent=self.hop_percent,
                                                 fs=self.fs,
                                                 zp_percent=self.zp_percent,
                                                 trim=self.trim,
                                                 verbose=self.verbose,
                                                 batch_size=self.batch_size,
                                                 shuffle_file_list=self.shuffle_file_list,
                                                 name=self.dataset_name)
        val_num = val_dataset.num_samples

        # Create training dataloader
        train_dataloader = data.DataLoader(train_dataset, 
                                           batch_size=self.batch_size,
                                           shuffle=self.shuffle_samples_in_batch,
                                           num_workers = self.num_workers)

        # Create validation dataloader
        val_dataloader = data.DataLoader(val_dataset, 
                                         batch_size=self.batch_size,
                                         shuffle=self.shuffle_samples_in_batch,
                                         num_workers = self.num_workers)
        return train_dataloader, val_dataloader, train_num, val_num

    def get_basic_info(self):
        basic_info = []
        basic_info.append('HOSTNAME: ' + self.hostname)
        basic_info.append('Time: ' + self.date)
        basic_info.append('Training results will be saved in: ' + self.save_dir)
        basic_info.append('Device for training: ' + self.device)
        if self.device == 'cuda':
            basic_info.append('Cuda verion: {}'.format(torch.version.cuda))
        basic_info.append('Model name: {}'.format(self.model_name))
        return basic_info

class BuildFFNN(BuildBasic):

    """
    Feed-forward fully-connected VAE
    Implementation of FFNN in rvae
    """

    def __init__(self, cfg=myconf()):
        
        super().__init__(cfg)

        # Load special parameters for FFNN
        self.x_dim = self.cfg.getint('Network', 'x_dim')
        self.z_dim = self.cfg.getint('Network','z_dim')
        self.hidden_dim_enc = [int(i) for i in self.cfg.get('Network', 'hidden_dim_enc').split(',')] # this parameter is a python list
        self.activation = eval(self.cfg.get('Network', 'activation'))
        
        # Create directory for results
        self.tag = "{}_{}_{}_z_dim={}".format(self.dataset_name, 
                                              self.date, 
                                              self.model_name, 
                                              self.z_dim)
        self.tag_simple = self.model_name
        self.save_dir = os.path.join(self.path_prefix, self.tag)
        if not(os.path.isdir(self.save_dir)):
            os.makedirs(self.save_dir)

        # Create logger
        log_file = os.path.join(self.save_dir, 'log.txt')
        logger = get_logger(log_file, self.logger_type)
        for log in self.get_basic_info():
            logger.info(log)
        logger.info('In this experiment, result will be saved in: ' + self.save_dir)
        self.logger = logger

        # Re-define data type
        self.get_seq = False

        self.build()

    def build(self):

        # Init VAE network
        self.logger.info('===== Init RVAE =====')
        self.model = VAE(x_dim = self.x_dim,
                         z_dim = self.z_dim,
                         hidden_dim_enc = self.hidden_dim_enc,
                         batch_size = self.batch_size,
                         activation = self.activation).to(self.device)
        
        # Print model information
        for log in self.model.get_info():
            self.logger.info(log)

        # Init optimizer (Adam by default)
        if self.optimization == 'adam':
            self.optimizer = torch.optim.Adam(self.model.parameters(), lr=self.lr)
        else:
            self.optimizer = torch.optim.Adam(self.model.parameters(), lr=self.lr)


class BuildRVAE(BuildBasic):
    """
    Reccurrent (uni- or bi-directional LSTM) VAE (RVAE)
    We can choose wheter there is a recurrence over z
    """
    def __init__(self, cfg = myconf()):

        super().__init__(cfg)

        # Load special paramters for RVAE
        self.x_dim = self.cfg.getint('Network', 'x_dim')
        self.z_dim = self.cfg.getint('Network','z_dim')
        self.bidir_enc_x = self.cfg.getboolean('Network', 'bidir_enc_x')
        self.h_dim_x = self.cfg.getint('Network', 'h_dim_x')
        self.num_LSTM_x = self.cfg.getint('Network', 'num_LSTM_x')
        self.rec_over_z = self.cfg.getboolean('Network', 'rec_over_z')
        self.h_dim_z = self.cfg.getint('Network', 'h_dim_z')
        self.num_LSTM_z = self.cfg.getint('Network', 'num_LSTM_z')
        self.hidden_dim_enc = [int(i) for i in self.cfg.get('Network', 'hidden_dim_enc').split(',')] # this parameter is a python list
        self.bidir_dec = self.cfg.getboolean('Network', 'bidir_dec')
        self.h_dim_dec = self.cfg.getint('Network', 'h_dim_dec')
        self.num_LSTM_dec = self.cfg.getint('Network', 'num_LSTM_dec')

        # Create directory for results
        if self.bidir_enc_x:
            enc_type = 'BiEnc'
        else:
            enc_type = 'UniEnc'
        if self.bidir_dec:
            dec_type = 'BiDec'
        else:
            dec_type = 'UniDec'
        if self.rec_over_z:
            posterior_type = 'RecZ'
        else:
            posterior_type = 'NoRecZ'
        fullname = '{}_{}_{}'.format(enc_type, dec_type, posterior_type)
        self.tag = "{}_{}_{}_z_dim={}".format(self.dataset_name, 
                                              self.date, 
                                              fullname, 
                                              self.z_dim)
        self.tag_simple = '{}{} {}'.format(enc_type[:-3], 'RNN', posterior_type)                                     
        self.save_dir = os.path.join(self.path_prefix, self.tag)
        if not(os.path.isdir(self.save_dir)):
            os.makedirs(self.save_dir)

        # Create logger
        log_file = os.path.join(self.save_dir, 'log.txt')
        logger = get_logger(log_file, self.logger_type)
        for log in self.get_basic_info():
            logger.info(log)
        logger.info('In this experiment, result will be saved in: ' + self.save_dir)
        self.logger = logger

        # Re-define data type
        self.get_seq = True

        self.build()
    
    def build(self):
        
        # Init RVAE network
        self.logger.info('===== Init RVAE =====')
        self.model = RVAE(x_dim=self.x_dim, z_dim=self.z_dim, batch_size=self.batch_size, 
                          bidir_enc_x=self.bidir_enc_x, h_dim_x=self.h_dim_x, 
                          num_LSTM_x=self.num_LSTM_x,
                          rec_over_z=self.rec_over_z, h_dim_z=self.h_dim_z, 
                          num_LSTM_z=self.num_LSTM_z,
                          hidden_dim_enc=self.hidden_dim_enc,
                          bidir_dec=self.bidir_dec, h_dim_dec=self.h_dim_dec, 
                          num_LSTM_dec=self.num_LSTM_dec,
                          device=self.device).to(self.device)
        # Print model information
        for log in self.model.get_info():
            self.logger.info(log)
            
        # Init optimizer (Adam by default)
        if self.optimization == 'adam':
            self.optimizer = torch.optim.Adam(self.model.parameters(), lr=self.lr)
        else:
            self.optimizer = torch.optim.Adam(self.model.parameters(), lr=self.lr)


def build_model(config_file='config_default.ini'):
    cfg = myconf()
    cfg.read(config_file)
    model_name = cfg.get('Network', 'name')
    if model_name == 'FFNN':
        model = BuildFFNN(cfg)
    elif model_name == 'RVAE':
        model = BuildRVAE(cfg)
    return model


if __name__ == '__main__':
    model = build_model('cfg_debug_ffnn.ini')
    net = model.net
    optimizer = model.optimizer
    model.print_model()
    train_dataloader, _, _, _ = model_class.build_dataloader()
