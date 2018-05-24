import vision
import config
import numpy as np
import pyosr
import uw_random

def get_view_cfg(args):
    VIEW_CFG = config.VIEW_CFG
    if args.viewset == 'cube':
        VIEW_CFG = [(0, 4), (90, 1), (-90, 1)]
    elif args.viewset == '14' or (not args.viewset and args.ferev >= 4):
        VIEW_CFG = config.VIEW_CFG_REV4
    elif args.viewset == '22' or (not args.viewset and args.ferev != 1):
        VIEW_CFG = config.VIEW_CFG_REV2
    view_array = vision.create_view_array_from_config(VIEW_CFG)
    if args.view >= 0:
        view_num = 1
    else:
        view_num = len(view_array)
    return view_num, view_array

def create_renderer(args, creating_ctx=True):
    view_num, view_array = get_view_cfg(args)
    w = h = args.res

    if creating_ctx:
        dpy = pyosr.create_display()
        glctx = pyosr.create_gl_context(dpy)
    r = pyosr.Renderer()
    if args.avi:
        r.avi = True
    r.pbufferWidth = w
    r.pbufferHeight = h
    r.setup()
    r.loadModelFromFile(args.envgeo)
    r.loadRobotFromFile(args.robgeo)
    r.scaleToUnit()
    r.angleModel(0.0, 0.0)
    r.default_depth = 0.0

    if args.view >= 0:
        if args.obview >= 0:
            va = [view_array[args.obview]]
        else:
            va = [view_array[args.view]]
    else:
        va = view_array
    r.views = np.array(va, dtype=np.float32)
    return r

def actions_to_adist_array(actions):
    n = len(actions)
    adists = np.zeros(
            shape=(n, 1, uw_random.DISCRETE_ACTION_NUMBER),
            dtype=np.float32)
    for i in range(n):
        adists[i, 0, actions[i]] = 1.0
    return adists

SC_PRED_PERMUTATION = 1
SC_ACTION_PERMUTATION = 2
