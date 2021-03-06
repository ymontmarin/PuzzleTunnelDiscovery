#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright © 2020 The University of Texas at Austin
# SPDX-FileContributor: Xinya Zhang <xinyazhang@utexas.edu>
# SPDX-License-Identifier: GPL-2.0-or-later
# -*- coding: utf-8 -*-

import numpy as np
import os
import multiprocessing
import copy

from . import solve
from . import choice_formatter
from . import util
from . import parse_ompl
from . import matio
try:
    import pygeokey
except ImportError as e:
    util.warn("[WARNING] CANNOT IMPORT pygeokey. This node is incapable of geometric based prediction")

class WorkerArgs(object):
    pass

def get_task_args(ws, args, per_geometry, FMT=util.UNSCREENED_KEY_PREDICTION_FMT, pairing=False):
    task_args = []
    for puzzle_fn, puzzle_name in ws.test_puzzle_generator():
        cfg, config = parse_ompl.parse_simple(puzzle_fn)
        wag = WorkerArgs()
        wag.dir = ws.dir
        wag.args = args
        wag.current_trial = ws.current_trial
        wag.puzzle_fn = puzzle_fn
        wag.puzzle_name = puzzle_name
        wag.env_fn = cfg.env_fn
        wag.rob_fn = cfg.rob_fn
        wag.FMT = FMT
        if args.no_refine:
            wag.refined_env_fn = cfg.env_fn
            wag.refined_rob_fn = cfg.rob_fn
        else:
            wag.refined_env_fn = cfg.refined_env_fn
            wag.refined_rob_fn = cfg.refined_rob_fn
        if per_geometry or pairing:
            wag.geo_type = 'env'
            wag.geo_fn = cfg.env_fn
            wag.refined_geo_fn = wag.refined_env_fn
            wag1 = copy.deepcopy(wag)
            wag.geo_type = 'rob'
            wag.geo_fn = cfg.rob_fn
            wag.refined_geo_fn = wag.refined_rob_fn
            wag2 = copy.deepcopy(wag)
            if pairing:
                task_args.append((wag1, wag2))
            else:
                task_args.append(wag1)
                task_args.append(wag2)
        else:
            task_args.append(copy.deepcopy(wag))
    return task_args

def refine_mesh(args, ws):
    if args.no_refine:
        util.ack('[refine_mesh] --no_refine is specified so the mesh will not be refined')
        return
    target_v = ws.config.getint('GeometriK', 'FineMeshV')
    task_args = get_task_args(ws, args=args, per_geometry=True)
    for wag in task_args:
        if os.path.isfile(wag.refined_geo_fn):
            continue
        # util.shell(['/usr/bin/env'])
        util.shell(['./TetWild', '--level', '6', '--targeted-num-v', str(target_v), '--output-surface', wag.refined_geo_fn, wag.geo_fn])

def detect_geratio_feature_worker(ws, wag):
    kpp = pygeokey.KeyPointProber(wag.geo_fn)
    natt = ws.config.getint('GeometriK', 'KeyPointAttempts')
    util.log("[sample_key_point] probing {} for {} attempts".format(wag.geo_fn, natt))
    pts = kpp.probe_key_points(natt)
    return pts

def detect_notch_feature_worker(ws, wag):
    util.log("[sample_key_point] Probing notches for {}".format(wag.refined_geo_fn))
    kpp2 = pygeokey.KeyPointProber(wag.refined_geo_fn)
    npts = kpp2.probe_notch_points()
    return npts

def _sample_key_point_worker(wag):
    ws = util.create_workspace_from_args(args)
    ws.current_trial = wag.current_trial
    pts = detect_geratio_feature_worker(ws, wag)
    SAMPLE_NOTCH = ws.config.getboolean('GeometriK', 'EnableNotchDetection', fallback=True)
    kps_fn = ws.keypoint_prediction_file(wag.puzzle_name, wag.geo_type)
    if SAMPLE_NOTCH:
        npts = detect_notch_feature_worker(ws, wag)
        util.log("[sample_key_point] writing {} points and {} notches to {}".format(
                  pts.shape[0], npts.shape[0], kps_fn))
        np.savez(kps_fn, KEY_POINT_AMBIENT=pts, NOTCH_POINT_AMBIENT=npts)
    else:
        util.log("[sample_key_point] writing {} points to {}".format(pts.shape[0], kps_fn))
        np.savez(kps_fn, KEY_POINT_AMBIENT=pts)

def _debug_notch_worker(wag):
    ws = util.create_workspace_from_args(wag.args)
    ws.current_trial = wag.current_trial
    kpp = pygeokey.KeyPointProber(wag.refined_env_fn)
    os.makedirs(ws.local_ws('debug'), exist_ok=True)
    kps_fn = ws.local_ws('debug', f'notch-{ws.current_trial}.npz')
    dic = dict()
    SKV = kpp.get_all_skeleton_points()
    SKE = kpp.get_skeleton_edges()
    SKVd = np.concatenate([SKV,SKV], axis=0)
    SKF = np.zeros((SKE.shape[0], 3), dtype=SKE.dtype)
    SKF[:, 0] = SKE[:, 0]
    SKF[:, 1] = SKE[:, 1]
    SKF[:, 2] = SKE[:, 0] + SKV.shape[0]
    import pyosr
    pyosr.save_obj_1(SKVd, SKF, ws.local_ws('debug', f'ske-{ws.current_trial}.obj'))
    # pyosr.save_obj_1(SKV, SKE, ws.local_ws('debug', f'ske-{ws.current_trial}.obj'))
    # pyosr.save_ply_2(SKV, SKE, np.zeros([]), np.array([]), ws.local_ws('debug', f'ske-{ws.current_trial}.ply'))
    kpp.local_min_thresh = 0.10
    kpp.group_tolerance_epsilon = 0.05
    for i in range(1):
        npts = kpp.probe_notch_points(seed=0, keep_intermediate_data=True)
        ZF = np.zeros(shape=(0,0))
        for it in range(3):
            P1 = kpp.get_intermediate_data(it, 0)
            P2 = kpp.get_intermediate_data(it, 1)
            P3 = kpp.get_intermediate_data(it, 2)
            pyosr.save_obj_1(P1, ZF, ws.local_ws('debug', f'P1-I{it}-{ws.current_trial}.obj'))
            pyosr.save_obj_1(P2, ZF, ws.local_ws('debug', f'P2-I{it}-{ws.current_trial}.obj'))
            pyosr.save_obj_1(P3, ZF, ws.local_ws('debug', f'P3-I{it}-{ws.current_trial}.obj'))
            PE = np.concatenate((P2, P3, P3),axis=0)
            D = P2.shape[0]
            edges = [(i, i + D, i + D*2) for i in range(D)]
            pyosr.save_obj_1(PE, edges, ws.local_ws('debug', f'PE-I{it}-{ws.current_trial}.obj'))
        npt1 = npts[:,:3]
        npt2 = npts[:,3:6]
        D = npt1.shape[0]
        nptb = np.concatenate((npt1, npt2, npt2),axis=0)
        edges = [(i, i + D, i + D*2) for i in range(D)]
        pyosr.save_obj_1(nptb, edges, ws.local_ws('debug', f'NPTE-{ws.current_trial}.obj'))
        matio.savetxt(ws.local_ws('debug', f'EL-{ws.current_trial}.txt'), np.linalg.norm(npt1 - npt2, axis=1))
        dic[str(i)] = npts
    np.savez(kps_fn, **dic)

def _debug_notch(args, ws):
    task_args = get_task_args(ws, args=args, per_geometry=False)
    for wag in task_args:
        _debug_notch_worker(wag)

def sample_key_point(args, ws):
    task_args = get_task_args(ws, args=args, per_geometry=True)
    USE_MP = False
    if USE_MP:
        pcpu = multiprocessing.Pool()
        pcpu.map(_sample_key_point_worker, task_args)
    else:
        for wag in task_args:
            _sample_key_point_worker(wag)

def _sample_key_conf_worker(wag):
    ws = util.create_workspace_from_args(args)
    FMT = wag.FMT
    kfn = ws.keyconf_file_from_fmt(wag.puzzle_name, FMT)
    util.log('[sample_key_conf] trial {}'.format(ws.current_trial))
    util.log('[sample_key_conf] sampling to {}'.format(kfn))
    ks = pygeokey.KeySampler(wag.env_fn, wag.rob_fn)
    INTER_CLASS_PREDICTION = True # For debugging. This must be enabled in order to predict notch-tooth key confs
    if INTER_CLASS_PREDICTION:
        def _load_kps(geo_type):
            kps_fn = ws.keypoint_prediction_file(wag.puzzle_name, geo_type)
            d = matio.load(kps_fn)
            return util.access_keypoints(d, geo_type)
        env_kps = _load_kps('env')
        rob_kps = _load_kps('rob')
        util.log("env_kps {}".format(env_kps.shape))
        util.log("rob_kps {}".format(rob_kps.shape))
        kqs, env_keyid, rob_keyid = ks.get_all_key_configs(env_kps, rob_kps,
                                           ws.config.getint('GeometriK', 'KeyConfigRotations'))
        util.log("kqs {}".format(kqs.shape))
    uw = util.create_unit_world(wag.puzzle_fn)
    cfg, config = parse_ompl.parse_simple(wag.puzzle_fn)
    iq = parse_ompl.tup_to_ompl(cfg.iq_tup)
    gq = parse_ompl.tup_to_ompl(cfg.gq_tup)
    # ompl_q = uw.translate_vanilla_to_ompl(kqs) <- this is buggy?
    unit_q = uw.translate_vanilla_to_unit(kqs)
    ompl_q = uw.translate_unit_to_ompl(unit_q)
    ompl_q = np.concatenate((iq, gq, ompl_q), axis=0)
    #np.savez(kfn, KEYQ_AMBIENT_NOIG=kqs, KEYQ_OMPL=ompl_q)
    np.savez(kfn, KEYQ_OMPL=ompl_q, ENV_KEYID=env_keyid, ROB_KEYID=rob_keyid)
    util.log('[sample_key_conf] save {} key confs to {}'.format(ompl_q.shape, kfn))

    unit_q = uw.translate_vanilla_to_unit(kqs)
    out = kfn+'.unit.txt'
    util.log('[debug][sample_key_conf] save unitary {} key confs to {}'.format(ompl_q.shape, out))
    np.savetxt(out, unit_q)

def sample_key_conf(args, ws):
    task_args = get_task_args(ws, args=args, per_geometry=False)
    for wag in task_args:
         _sample_key_conf_worker(wag)
    # pcpu = multiprocessing.Pool()
    # pcpu.map(_sample_key_conf_worker, task_args)

def sample_key_conf_with_geometrik_prefix(args, ws):
    task_args = get_task_args(ws, args=args, per_geometry=False, FMT=util.GEOMETRIK_KEY_PREDICTION_FMT)
    for wag in task_args:
         _sample_key_conf_worker(wag)

def deploy_geometrik_to_condor(args, ws):
    ws.deploy_to_condor(util.WORKSPACE_SIGNATURE_FILE,
                        util.WORKSPACE_CONFIG_FILE,
                        util.CONDOR_TEMPLATE,
                        util.TESTING_DIR+'/')

function_dict = {
        'refine_mesh' : refine_mesh,
        'sample_key_point' : sample_key_point,
        'sample_key_conf' : sample_key_conf,
        'sample_key_conf_with_geometrik_prefix' : sample_key_conf_with_geometrik_prefix,
        'deploy_geometrik_to_condor' : deploy_geometrik_to_condor,
        '_debug_notch' : _debug_notch,
}

def setup_parser(subparsers, module_name='geometrik', function_dict=function_dict):
    p = subparsers.add_parser(module_name, help='Sample Key configuration from Geometric features',
                              formatter_class=choice_formatter.Formatter)
    p.add_argument('--stage',
                   choices=list(function_dict.keys()),
                   help='R|Possible stages:\n'+'\n'.join(list(function_dict.keys())),
                   default='',
                   metavar='')
    p.add_argument('--only_wait', action='store_true')
    p.add_argument('--no_refine', help='Do not refine the mesh with TetWild, nor use the refined version in later stages', action='store_true')
    util.set_common_arguments(p)

def run(args):
    if args.stage in function_dict:
        ws = util.create_workspace_from_args(args)
        function_dict[args.stage](args, ws)
    else:
        print("Unknown geometrik pipeline stage {}".format(args.stage))

def _remote_command(ws, cmd, auto_retry=True):
    ws.remote_command(ws.condor_host,
                      ws.condor_exec(),
                      ws.condor_ws(),
                      'geometrik', cmd, with_trial=True, auto_retry=auto_retry)

def remote_refine_mesh(ws):
    _remote_command(ws, 'refine_mesh')

def remote_sample_key_point(ws):
    _remote_command(ws, 'sample_key_point')

def remote_sample_key_conf(ws):
    _remote_command(ws, 'sample_key_conf')

def remote_sample_key_conf_with_geometrik_prefix(ws):
    _remote_command(ws, 'sample_key_conf_with_geometrik_prefix')

def collect_stages(variant=0):
    if variant in [0]:
        ret = [ ('deploy_to_condor',
                  lambda ws: ws.deploy_to_condor(util.WORKSPACE_SIGNATURE_FILE,
                                                 util.WORKSPACE_CONFIG_FILE,
                                                 util.CONDOR_TEMPLATE,
                                                 util.TESTING_DIR+'/')
                ),
                ('refine_mesh', remote_refine_mesh),
                ('sample_key_point', remote_sample_key_point),
                ('sample_key_conf', remote_sample_key_conf),
                #('deploy_geometrik_to_condor', lambda ws: deploy_geometrik_to_condor(None, ws))
              ]
    elif variant in [4]:
        ret = [
                ('refine_mesh', remote_refine_mesh),
                ('sample_key_point', remote_sample_key_point),
                ('sample_key_conf_with_geometrik_prefix', remote_sample_key_conf_with_geometrik_prefix),
                #('deploy_geometrik_to_condor', lambda ws: deploy_geometrik_to_condor(None, ws))
              ]
    else:
        assert False, f'[geometrik] Unknown variant {variant}'
    return ret
