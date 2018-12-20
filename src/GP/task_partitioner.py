import numpy as np
import os

def _fn_touch_q(out_dir, vert_id, batch_id):
    return "{}/touchq-{}-{}.npz".format(out_dir, vert_id, batch_id)

def _fn_isectgeo(out_dir, vert_id, conf_id):
    return "{}/isectgeo-from-vert-{}-{}.obj".format(out_dir, vert_id, conf_id)

def _fn_uvgeo(out_dir, geo_type, vert_id, conf_id):
    return "{}/{}-uv-from-vert-{}-{}.obj".format(out_dir, geo_type, vert_id, conf_id)

def atlas_fn(out_dir, geo_type, vert_id, index=None, nw=False):
    nwsuffix = "" if not nw else "-nw"
    if index is None:
        return "{}/atlas-{}-from-vert-{}{}.npz".format(out_dir, geo_type, vert_id, nwsuffix)
    else:
        return "{}/atlas-{}-from-vert-{}-{}{}.npz".format(out_dir, geo_type, vert_id, index, nwsuffix)

def _fn_atlas2prim(out_dir, geo_type):
    return "{}/atlas2prim-{}.npz".format(out_dir, geo_type)

def tqre_fn(io_dir, vert_id, batch_id):
    return "{}/touchq_re-from-vert-{}-{}.npz".format(io_dir, vert_id, batch_id)

def tqrevis_fn(io_dir, vert_id, batch_id):
    return "{}/touchq_re_vis-from-vert-{}-{}.npz".format(io_dir, vert_id, batch_id)

class TaskPartitioner(object):
    '''
    iodir: input/output directory. all task files should be there.
    gp_batch: size of geometry processing batch. Task granularity of `isectgeo` and `uv`
    tq_batch: size of touch configuration batch. Task granularity of `run`
              Note geometry processing needs the touch configuration info.

    Note: surprisingly gp_batch and tq_batch can be None for over half of the commands.
    '''
    def __init__(self, iodir, gp_batch, tq_batch, tunnel_v):
        self._iodir = iodir
        if gp_batch is not None:
            assert tq_batch % gp_batch == 0, "GeoP Batch Size % Touch Batch Size must be 0"
            '''
            Batch subdivider, geometry processing is consider more expensive than tq sampling
            '''
            self._gp_per_tq = tq_batch / gp_batch
        self._gp_batch = gp_batch
        self._tq_batch = tq_batch
        self.tunnel_v = tunnel_v

    '''
    Task vector is resized into (batch_id, vertex_id) matrix
    '''
    def get_batch_vert_index(self, task_id):
        return divmod(task_id, len(self.tunnel_v))

    def get_vert_id(self, task_id):
        return self.get_batch_vert_index(task_id)[1]

    def get_batch_id(self, task_id):
        return self.get_batch_vert_index(task_id)[0]

    def get_tunnel_vertex(self, task_id):
        return self.tunnel_v[self.get_vert_id(task_id)]

    def get_tq_batch_size(self):
        return self._tq_batch

    def _task_id_gp_to_tq(self, task_id):
        return divmod(task_id, self._gp_per_tq)

    '''
    Functions gen_touch_q
    Return a generator that "pumps" touch along with its attributes from a given (GeoP) task id
    '''
    def gen_touch_q(self, task_id, members=['TOUCH_V', 'IS_INF']):
        def tqgen(npd, start, size, vert_id, conf_id_base, members):
            sample_array = [d[n] for n in members]
            for i in range(size):
                vc = [vert_id, conf_id_base + start + i]
                sample = [array[start+i] for array in sample_array]
                yield sample + vc
        tq_task_id, remainder = self._task_id_gp_to_tq(task_id)
        d = np.load(self.get_tq_fn(tq_task_id))
        return tqgen(d,
                remainder * self._gp_batch, self._gp_batch,
                self.get_vert_id(tq_task_id),
                self.get_batch_id(tq_task_id) * self._tq_batch,
                members=members)

    '''
    Functions to get I/O file name
    Note: we use (vertex id, configuration id) to uniquely locate a file for geometry processing.
          This tuple is generated by the generator returned from gen_touch_q
    '''
    def get_tq_fn(self, task_id):
        batch_id, vert_id = self.get_batch_vert_index(task_id)
        return _fn_touch_q(out_dir=self._iodir, vert_id=vert_id, batch_id=batch_id)

    def get_isect_fn(self, vert_id, conf_id):
        return _fn_isectgeo(out_dir=self._iodir, vert_id=vert_id, conf_id=conf_id)

    def get_uv_fn(self, geo_type, vert_id, conf_id):
        return _fn_uvgeo(self._iodir, geo_type, vert_id, conf_id)

    def get_atlas_fn(self, geo_type, task_id):
        batch_id, vert_id = self.get_batch_vert_index(task_id)
        return atlas_fn(self._iodir, geo_type, vert_id, None)

    def get_atlas2prim_fn(self, geo_type):
        return _fn_atlas2prim(self._iodir, geo_type)

    def get_tqre_fn(self, task_id):
        batch_id, vert_id = self.get_batch_vert_index(task_id)
        return tqre_fn(self._iodir, vert_id=vert_id, batch_id=batch_id)

    def get_tqrevis_fn(self, task_id):
        batch_id, vert_id = self.get_batch_vert_index(task_id)
        return tqrevis_fn(self._iodir, vert_id=vert_id, batch_id=batch_id)

class ObjGenerator(object):
    def __init__(self, in_dir, vert_id):
        self.in_dir = in_dir
        self.vert_id = vert_id
        self.per_vertex_conf_id = 0

    def __iter__(self):
        return self

    def __next__(self):
        fn = _fn_isectgeo(out_dir=self.in_dir,
                          vert_id=self.vert_id,
                          conf_id=self.per_vertex_conf_id)
        if not os.path.exists(fn):
            raise StopIteration
        print("loading {}".format(fn))
        self.per_vertex_conf_id += 1
        return pyosr.load_obj_1(fn)

    # Python 2 compat
    def next(self):
        return self.__next__()

class UVObjGenerator(object):
    def __init__(self, in_dir, geo_type, vert_id):
        self.in_dir = in_dir
        self.geo_type = geo_type
        self.vert_id = vert_id
        self.conf_id = 0

    def __iter__(self):
        return self

    def __next__(self):
        fn = _fn_uvgeo(self.in_dir, self.geo_type, self.vert_id, self.conf_id)
        self.conf_id += 1
        print("loading {}".format(fn))
        if not os.path.exists(fn):
            return None, None # Note: do NOT raise StopIteration, we may miss some file in the middle
        return pyosr.load_obj_1(fn)

    # Python 2 compat
    def next(self):
        return self.__next__()


class TouchQGenerator(object):
    def __init__(self, in_dir, vert_id):
        self.in_dir = in_dir
        self.vert_id = vert_id
        self.tq_batch_id = 0
        self.tq_local_id = 0
        self.tq = None

    def __iter__(self):
        return self

    def __next__(self):
        if self.tq is None:
            tq_fn = _fn_touch_q(out_dir=self.in_dir,
                                vert_id=self.vert_id,
                                batch_id=self.tq_batch_id)
            try:
                print("loading {}".format(tq_fn))
                d = np.load(tq_fn)
                self.tq = d['TOUCH_V']
                self.tq_size = len(self.tq)
                self.inf = d['IS_INF']
                self.tq_local_id = 0
            except IOError:
                raise StopIteration
        ret = (self.tq[self.tq_local_id], self.inf[self.tq_local_id])
        self.tq_local_id += 1
        if self.tq_local_id >= self.tq_size:
            self.tq_batch_id += 1
            self.tq_local_id = 0
            self.tq = None
        return ret

    # Python 2 compat
    def next(self):
        return self.__next__()
