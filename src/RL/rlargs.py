import argparse
import config
import aniconf12 as aniconf

def get_parser():
    parser = argparse.ArgumentParser(description='Process some integers.', formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument('--envgeo', help='Path to environment geometry',
            default=aniconf.env_fn)
    parser.add_argument('--robgeo', help='Path to robot geometry',
            default=aniconf.rob_fn)
    parser.add_argument('--ckptdir', help='Path for checkpoint files',
            default='ckpt/pretrain-d/')
    parser.add_argument('--sampleout', help='Path to store generated samples',
            default='')
    parser.add_argument('--mispout', help='Path to store mispredicted samples',
            default='')
    parser.add_argument('--samplein', help='Path to load generated samples',
            default='')
    parser.add_argument('--sampletouse',  metavar='NUMBER',
            help='Number of samples to use during the training',
            type=int, default=-1)
    parser.add_argument('--samplebase',  metavar='NUMBER',
            help='Base Number of samples to read/write',
            type=int, default=0)
    parser.add_argument('--uniqueaction',  metavar='NUMBER',
            help='Only generate a specific action when sampling actions',
            type=int, default=-1)
    parser.add_argument('--actionset', nargs='+',
            help='Set to sample actions within, -1 means all actions (0-11)',
            type=int,
            default=[])
    parser.add_argument('--ckptprefix', help='Prefix of checkpoint files',
            default='pretrain-d-ckpt')
    parser.add_argument('--device', help='Prefix of GT file names generated by aa-gt.py',
            default='/gpu:0')
    parser.add_argument('--batch', metavar='NUMBER',
            help='Batch size of each iteration in training, also serves as T_MAX in A3C/A2C algo.',
            type=int, default=32)
    parser.add_argument('--samplebatching', metavar='NUMBER',
            help='Number of samples to aggregrate in training',
            type=int, default=1)
    parser.add_argument('--ereplayratio', metavar='N',
            help='Set the experience replay buffer to N*batch samples. <=0 disables experience replay',
            type=int, default=-1)
    parser.add_argument('--queuemax', metavar='NUMBER',
            help='Capacity of the synchronized queue to store generated GT',
            type=int, default=32)
    parser.add_argument('--threads', metavar='NUMBER',
            help='Number of GT generation threads',
            type=int, default=1)
    parser.add_argument('--iter', metavar='NUMBER',
            help='Number of samples to generate by each thread',
            type=int, default=0)
    parser.add_argument('--istateraw', metavar='REAL NUMBER',
            nargs='+',
            help='Initial state in original scaling',
            type=float, default=[17.97,7.23,10.2,1.0,0.0,0.0,0.0])
    parser.add_argument('--amag', metavar='REAL NUMBER',
            help='Magnitude of discrete actions',
            type=float, default=0.0125 * 4)
    parser.add_argument('--vmag', metavar='REAL NUMBER',
            help='Magnitude of verifying action',
            type=float, default=0.0125 * 4 / 8)
    parser.add_argument('-n', '--dryrun',
            help='Visualize the generated GT without training anything',
            action='store_true')
    parser.add_argument('--dryrun2',
            help='Visualize the generated GT without training anything (MT version)',
            action='store_true')
    parser.add_argument('--dryrun3',
            help='Only generated GT, and store the GT if --sampleout is provided',
            action='store_true')
    parser.add_argument('--elu',
            help='Use ELU instead of ReLU after each NN layer',
            action='store_true')
    parser.add_argument('--lstm',
            help='Add LSTM after feature extractor for PolNet and ValNet',
            action='store_true')
    parser.add_argument('--singlesoftmax',
            help='Do not apply softmax over member of committee. Hence only one softmax is used to finalize the prediction',
            action='store_true')
    parser.add_argument('--featnum',
            help='Size of the feature vector (aka number of features)',
            type=int, default=256)
    parser.add_argument('--imhidden',
            help='Inverse Model Hidden Layer',
            nargs='+', type=int, default=[])
    parser.add_argument('--fwhidden',
            help='Forward Model Hidder Layer',
            nargs='+', type=int, default=[1024, 1024])
    parser.add_argument('--fehidden',
            help='Feature Extractor Hidder Layer',
            nargs='+', type=int, default=[1024, 1024])
    parser.add_argument('--polhidden',
            help='Policy Network Hidder Layer',
            nargs='+', type=int, default=[1024, 1024])
    parser.add_argument('--valhidden',
            help='Value Network Hidder Layer',
            nargs='+', type=int, default=[1024, 1024])
    parser.add_argument('--eval',
            help='Evaluate the network, rather than training',
            action='store_true')
    parser.add_argument('--continuetrain',
            help='Continue an interrputed training from checkpoint. This basically loads epoch from the checkpoint. WARNING: THIS IS INCOMPATIBLE WITH --samplein',
            action='store_true')
    parser.add_argument('--ferev',
            help='Reversion of Feature Extractor',
            choices=range(1,12+1),
            type=int, default=1)
    parser.add_argument('--capture',
            help='Capture input image to summary',
            action='store_true')
    parser.add_argument('--committee',
            help='(deprecated by --viewinitckpt) Employ a committee of NNs with different weights to extract features/make decisions from different views',
            action='store_true')
    parser.add_argument('--norgbd',
            help='Do not store RGB/D images in storing the sample, to save disk spaces',
            action='store_true')
    parser.add_argument('--nosamplepreview',
            help='Do not store preview RGB images from generated samples, to save disk spaces',
            action='store_true')
    parser.add_argument('--view',
            help='Pickup one view to train',
            type=int, default=-1)
    parser.add_argument('--obview',
            help='The actual view used by renderer, defaults to --view but can be different for debugging purpose',
            type=int, default=-1)
    parser.add_argument('--sharedmultiview',
            help='Enable AdVanced Illumination mode',
            action='store_true')
    parser.add_argument('--viewinitckpt',
            help='Initialize independent views in sequence with given checkpoints. --eval must present if viewinitckpt is given',
            nargs='*', default=[])
    parser.add_argument('--res',
            help='Resolution',
            type=int, default=config.DEFAULT_RES)
    parser.add_argument('--avi',
            help='Enable AdVanced Illumination mode',
            action='store_true')
    parser.add_argument('--viewset',
            help='Choose set of views',
            choices=['cube', '14', '22'],
            default='')
    parser.add_argument('--egreedy',
            help='Epsilon Greedy Policy',
            type=float,
            nargs='*',
            default=[0.2])
    parser.add_argument('--sancheck',
            help='Different sanity check points',
            type=int,
            nargs='*',
            default=[])
    parser.add_argument('--visionformula',
            help='Load preset formulas for vision. Note this overrides other options',
            type=int,
            choices=[1],
            default=0)
    parser.add_argument('--agents',
            metavar='NUMBER',
            help='Use multiple agents PER-THREAD to generalize the model',
            type=int,
            default=-1)
    parser.add_argument('--permutemag',
            metavar='REAL',
            help='Magnitude of translation in the randomized permutation',
            type=float,
            default=0.0)
    parser.add_argument('--jointfw',
            help='Use the joint all views as the input of forward model',
            action='store_true')

    return parser

def parse():
    parser = get_parser()
    args = parser.parse_args()
    if args.visionformula == 1:
        args.elu = True
        args.res = 224
        args.avi = True
        args.ferev = 11
        args.viewset = 'cube'
        args.sharedmultiview = True
        args.featnum = 256
        args.imhidden = [256, 256]
    return args
