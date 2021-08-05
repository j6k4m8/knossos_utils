################################################################################
#
#  (C) Copyright 2015
#  Max-Planck-Gesellschaft zur Foerderung der Wissenschaften e.V.
#
#  chunky.py is free software: you can redistribute it and/or modify
#  it under the terms of the GNU General Public License version 2 of
#  the License as published by the Free Software Foundation.
#
#  This program is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU General Public License for more details.
#
#  For further information feel free to contact
#  Sven.Dorkenwald@mpimf-heidelberg.mpg.de
#
#
################################################################################


"""This file provides a class representation of a KNOSSOS-dataset for
reading and writing raw and overlay data."""

from typing import Tuple, Optional

import pickle as pkl
import glob
import h5py
from multiprocessing.pool import ThreadPool
from multiprocessing import Pool
import numpy as np
import os
import sys
import time
import itertools as it

import scipy.misc

from . import knossosdataset


def wrapper(func, args, kwargs):
    """wrapper function, calls a function with a variable number
    of args and kwargs

    Parameters:
    -----------
    kargs: list
    list of arguments depending on the function that is used
    kargs: dictionary
    keyword arguments stored in a dictionary
    """
    func(*args, **kwargs)


def _export_cset_as_kd_thread(args):
    """Helper function.
    TODO: refactor.
    """
    coords = args[0]
    size = np.copy(args[1])
    cset_path = args[2]
    kd_path = args[3]
    name = args[4]
    hdf5names = args[5]
    as_raw = args[6]
    unified_labels = args[7]
    nb_threads = args[8]
    orig_dtype = args[9]
    fast_downsampling = args[10]
    if len(args) == 12:
        mags2do = args[11]
    else:
        mags2do = None

    cset = load_dataset(cset_path, update_paths=True)

    # initialize KD object
    kd = knossosdataset.KnossosDataset()
    # TODO: set appropriate channel
    # # kd.set_channel(channel)
    if os.path.isfile(kd_path):
        kd.initialize_from_conf(kd_path)
    elif len(glob.glob(f'{kd_path}/*.pyk.conf')) == 1:
        pyk_confs = glob.glob(f'{kd_path}/*.pyk.conf')
        kd.initialize_from_pyknossos_path(pyk_confs[0])
    elif os.path.isfile(kd_path + "/mag1/knossos.conf"):
        # Initializes the dataset by parsing the knossos.conf in path + "mag1"
        kd_path += "/mag1/knossos.conf"
        kd.initialize_from_knossos_path(kd_path)
    else:
        raise ValueError(f'Could not find KnossosDataset config at {kd_path}.')

    for dim in range(3):
        if coords[dim] + size[dim] > cset.box_size[dim]:
            size[dim] = cset.box_size[dim] - coords[dim]

    data_dict = cset.from_chunky_to_matrix(size, coords, name, hdf5names, dtype=orig_dtype)
    data_list = []
    if unified_labels:
        for nb_hdf5_name in range(len(hdf5names)):
            curr_d = data_dict[hdf5names[nb_hdf5_name]]
            if (curr_d.dtype.kind not in ("u", "i")) and (0 < np.max(curr_d) <= 1.0):
                curr_d = (curr_d * 255).astype(np.uint8)
            data_list.append(np.array(curr_d > 0,
                                      dtype=np.uint8) * (nb_hdf5_name + 1))
            data_dict[hdf5names[nb_hdf5_name]] = []
        data_list = np.max(data_list, axis=0)
    else:
        curr_d = data_dict[hdf5names[0]]
        if (curr_d.dtype.kind not in ("u", "i")) and (0 < np.max(curr_d) <= 1.0):
            curr_d = (curr_d * 255).astype(np.uint8)
        data_list.append(curr_d)
        data_dict[hdf5names[0]] = []
        for nb_hdf5_name in range(1, len(hdf5names)):
            curr_d = data_dict[hdf5names[nb_hdf5_name]]
            if (curr_d.dtype.kind not in ("u", "i")) and (0 < np.max(curr_d) <= 1.0):
                curr_d = (curr_d * 255).astype(np.uint8)
            data_list[0] = np.maximum(data_list[0], curr_d)
            data_dict[hdf5names[nb_hdf5_name]] = []
        # TODO: this needed to be introduced at some point, make sure this behaves as
        #  originally with len(hdf5names) > 1.
        assert len(data_list) == 1
        data_list = data_list[0]
    # make it ZYX
    data_list = np.swapaxes(data_list, 0, 2)
    if mags2do is None:
        mags2do = kd.available_mags
    if as_raw:
        kd.save_raw(offset=coords, mags=mags2do, data=data_list, data_mag=1,
                    fast_resampling=fast_downsampling)
    else:
        kd.save_seg(offset=coords, mags=mags2do, data=data_list, data_mag=1,
                    fast_resampling=fast_downsampling)


def _export_cset_as_kd_control_thread(args):
    """ Helper function
    """
    coords = args[0]
    size = np.copy(args[1])
    cset_path = args[2]
    kd_path = args[3]
    name = args[4]
    hdf5names = args[5]
    as_raw = args[6]
    unified_labels = args[7]
    nb_threads = args[8]

    # initialize KD object
    kd = knossosdataset.KnossosDataset()
    # TODO: set appropriate channel
    # # kd.set_channel(channel)
    if os.path.isfile(kd_path):
        kd.initialize_from_conf(kd_path)
    elif len(glob.glob(f'{kd_path}/*.pyk.conf')) == 1:
        pyk_confs = glob.glob(f'{kd_path}/*.pyk.conf')
        kd.initialize_from_pyknossos_path(pyk_confs[0])
    elif os.path.isfile(kd_path + "/mag1/knossos.conf"):
        # Initializes the dataset by parsing the knossos.conf in path + "mag1"
        kd_path += "/mag1/knossos.conf"
        kd.initialize_from_knossos_path(kd_path)
    else:
        raise ValueError(f'Could not find KnossosDataset config at {kd_path}.')

    if as_raw:
        data = kd.load_raw(size=size, offset=coords, mag=1)
    else:
        data = kd.load_seg(size=size, offset=coords, mag=1)

    if np.sum(data) == 0:
        _export_cset_as_kd_thread(args)


def _export_cset_to_tiff_stack_thread(args):
    cset = args[0]
    save_path = args[1]
    name = args[2]
    hdf5names = args[3]
    z = args[4]
    stride = args[5]
    boundary = args[6]

    box_size = cset.box_size
    if stride + z > boundary[2]:
        stride = boundary[2] - z

    data_dict = cset.from_chunky_to_matrix([box_size[0], box_size[1], stride],
                                           [0, 0, z], name, hdf5names)

    for hdf5name in hdf5names:
        this_path = save_path + "/" + hdf5name + "/"
        if not os.path.exists(this_path):
            os.makedirs(this_path)
        for dz in range(stride):
            scipy.misc.imsave(this_path + "img_%.5d.png" % (z + dz),
                              data_dict[hdf5name]
                              [:boundary[0], :boundary[1], dz])


def _switch_array_entries(this_array, entries):
    """
    Switches to array entries

    Parameters
    ----------
    this_array: np.array
    entries: list of int

    Returns
    -------
    this_array: np.array
    """
    entry_0 = this_array[entries[0]]
    this_array[entries[0]] = this_array[entries[1]]
    this_array[entries[1]] = entry_0
    return this_array


def save_dataset(chunk_dataset):
    with open(chunk_dataset.path_head_folder + "/chunk_dataset.pkl", 'wb') \
            as output:
        pkl.dump(chunk_dataset, output, pkl.HIGHEST_PROTOCOL)


def load_dataset(path_head_folder, update_paths=True):
    with open(path_head_folder + "/chunk_dataset.pkl", 'rb') as f:
        this_cd = pkl.load(f)

    if update_paths:
        # print("Updating paths...")
        this_cd.path_head_folder = path_head_folder + '/'
        for key in this_cd.chunk_dict.keys():
            this_cd.chunk_dict[key].path_head_folder = path_head_folder + '/'
            if this_cd.chunk_dict[key].folder[-1] == '/':
                rel_path = this_cd.chunk_dict[key].folder.split('/')[-2]
            else:
                rel_path = this_cd.chunk_dict[key].folder.split('/')[-1]
            this_cd.chunk_dict[key].folder = path_head_folder + '/' + rel_path + '/'
        # print("... finished.")
        # save_dataset(this_cd)

    return this_cd


def update_dataset(cset, overwrite=True):
    up_cset = ChunkDataset()
    up_cset.initialize(cset.dataset, cset.box_size,
                       cset.chunk_size, cset.path_head_folder,
                       overlap=cset.overlap,
                       box_coords=cset.box_coords)
    if overwrite:
        save_dataset(up_cset)
    return up_cset


class ChunkDataset(object):
    """ Class that contains a dict of chunks after initializing it

    Parameters:
    -----------

    chunk_dict: dictionary of chunk objects
        contains all chunks of the chunk dataset
    """

    def __init__(self):
        self.chunk_dict = {}
        self.chunklist = []
        self.path_head_folder = []
        self.coord_dict = {}
        self.box_coords = []
        self.box_coords_list = []
        self.chunk_size = []
        self.feature_file_path = ''
        self.ann_dic = None
        self._dataset_path = ''
        self.box_size = None
        self.overlap = None

    @property
    def dataset(self):
        assert os.path.exists(self._dataset_path)
        kd = knossosdataset.KnossosDataset()
        kd.initialize_from_conf(self._dataset_path)
        return kd

    def initialize(self, knossos_dataset_object, box_size,
                   chunk_size, path_head_folder, overlap=None,
                   box_coords=None, fit_box_size=False,
                   mask_arr=None, mask_mag=None):
        """ Calculates the coordinates of all chunks and initializes them

        Parameters:
        -----------

        knossos_dataset_object: knossos dataset
            has to be initialized beforehand
        box_size: 3 sequence of int
            defines the size of the box without overlap
        box_coords: 3 sequence of int
            defines the coordinates of the box without overlap
        chunk_size: 3 sequence of int
            defines the size of each chunk without overlap
        overlap: 3 sequence of int
            defines the overlap of each chunk (and also of the box)
        mask_arr: np.ndarray
            Mask array that can be used instead of box_size and box_coords to specify where to create chunks for the
            dataset. Used with mask_mag.
        mask_mag: int
            Mag level (based on knossos_dataset_object) at which mask_arr is provided.


        Returns:
        --------

        nothing so far
        """

        if all((box_coords is None, box_size is None, mask_arr is not None, mask_mag is not None)):
            pass
        elif all((box_coords is not None, box_size is not None, mask_arr is None, mask_mag is None)):
            pass
        else:
            raise Exception('Must initialize ChunkDataset with either box_offset and box_size OR with '
                            'mask_arr and mask_mag')

        if overlap is None:
            overlap = np.zeros(3)

        if mask_arr is not None:
            mask_scale_ratio = knossos_dataset_object.scale_ratio(mask_mag, 1)
            chunk_size_mask_mag = np.ceil(chunk_size / mask_scale_ratio).astype(int)
            box_coords = (np.min(np.argwhere(mask_arr), axis=0) * mask_scale_ratio).astype(int)
            box_max = ((np.max(np.argwhere(mask_arr), axis=0) + 1) * mask_scale_ratio).astype(int)
            box_size = box_max - box_coords

        box_size = np.array(box_size)
        if fit_box_size:
            for dim in range(3):
                if not box_size[dim] % chunk_size[dim] == 0:
                    box_size[dim] += (chunk_size[dim] -
                                      (box_size[dim] % chunk_size[dim]))

        if False in np.equal(np.mod(box_size, chunk_size), np.zeros(3)):
            raise Exception("box_size has to be multiple of chunk_size")

        self.path_head_folder = path_head_folder
        self.chunk_size = np.array(chunk_size)
        self.box_coords = box_coords
        self._dataset_path = knossos_dataset_object.conf_path
        self.box_size = box_size
        self.overlap = overlap

        list_of_coords = []
        multiple = box_size // chunk_size
        for x in range(multiple[0]):
            for y in range(multiple[1]):
                for z in range(multiple[2]):
                    cur_chunk_offset = [
                        x * chunk_size[0] + box_coords[0],
                        y * chunk_size[1] + box_coords[1],
                        z * chunk_size[2] + box_coords[2]]
                    if mask_arr is not None:
                        cur_chunk_offset_mask_mag = np.floor(np.array(cur_chunk_offset) / mask_scale_ratio).astype(int)
                        cur_chunk_mask_slices = tuple(
                            slice(lo, lo+sz) for lo, sz in zip(cur_chunk_offset_mask_mag, chunk_size_mask_mag))
                        if np.sum(mask_arr[cur_chunk_mask_slices]) == 0:
                            continue
                    list_of_coords.append(cur_chunk_offset)

        for nb_coord, coord in enumerate(list_of_coords):
            new_chunk = Chunk()
            new_chunk.number = nb_coord
            new_chunk.coordinates = coord
            new_chunk._dataset_path = knossos_dataset_object.conf_path
            new_chunk.size = chunk_size
            new_chunk.overlap = overlap
            new_chunk.folder_name = 'chunky_%i/' % nb_coord

            self.chunk_dict[nb_coord] = new_chunk
            self.coord_dict[tuple(new_chunk.coordinates)] = nb_coord
            if path_head_folder:
                new_chunk.path_head_folder = path_head_folder
                new_chunk.folder = path_head_folder + "/" + new_chunk.folder_name
                new_chunk.box_size = box_size

    def rechunked_space(self, stride: Tuple[int, int, int]):
        """
        For the chunk grid defined by stride, return every chunk for which the ChunkDataset instance also
        contains a chunk.

        Use this, for example, to write into a KnossosDataset in a cube-aligned fashion.
        """

        rechunked = set()
        for cur_chunk in self.chunk_dict.values():
            cur_chunk_min, cur_chunk_sz = cur_chunk.coordinates, cur_chunk.size
            cur_chunk_max = tuple(xx + yy - 1 for xx, yy in zip(cur_chunk_min, cur_chunk_sz))
            rechunk_lo = tuple(yy * (xx // yy) for xx, yy in zip(cur_chunk_min, stride))
            rechunk_hi = tuple(yy * (1 + xx // yy) for xx, yy in zip(cur_chunk_max, stride))

            for x, y, z in it.product(*[range(lo, hi, step) for lo, hi, step in zip(rechunk_lo, rechunk_hi, stride)]):
                rechunked.add((x, y, z))

        return list(rechunked)

    def apply_to_subset(self, function, args=[], kwargs={}, chunklist=[],
                        with_chunk=True, with_chunkclass=False):
        """ calls a function and applies it to a variable number of chunks

        Parameters:
        -----------
        function_name: str
        name of the function to call
        module_name: str
        name of the module from which the function is imported
        chunklist: list
        defines subset of chunks to process (default: all chunks)
        args: list
        list of arguments depending on the function that is used
        kargs: dictionary
        keyword arguments stored in a dictionary
        with_chunk: boolean
        if True, chunk class is passed to the function (default: True)

        """

        if not chunklist:
            chunklist = list(range(len(self.chunk_dict)))
            print(self.chunklist)
        if self.chunklist:
            print('in loop')
            chunklist = self.chunklist

        for i in chunklist:
            ls = []
            if with_chunk:
                ls.append(self.chunk_dict[i])
            if with_chunkclass:
                ls.append(self)

            for i in args:
                ls.append(i)

            if [] in ls:
                ls.remove([])

            wrapper(function, ls, kwargs)

    def map_coordinates_on_chunks(self, coordinates):
        """ calculates a list of chunks containing the given coordinates

        Parameters:
        -----------
        coordinates: list of 3 sequences of int
            list of coordinates
        returns list of int of length coordinates
            chunk numbers containing the given coordinates
        """
        if not isinstance(coordinates, list):
            coordinates = coordinates.tolist()
        chunk_rep = []
        chunk_size = np.array(self.chunk_size, dtype=np.int32)
        if self.box_coords is not None:
            for coordinate in coordinates:
                chunk_coordinate = np.array(np.array(coordinate, np.int32) / #d (explicitly rounded to int, so type doesn't matter)
                                            chunk_size, dtype=np.int32) * chunk_size
                chunk_rep.append(self.coord_dict[tuple(chunk_coordinate)])
        else:
            for coordinate in coordinates:
                was_found =False
                coordinate = np.array(coordinate)
                for coord in self.coord_dict.keys():
                    if np.sum(coordinate >= np.array(coord)) == 3:
                        if np.sum(coordinate - self.chunk_size <= np.array(coord)) == 3:
                            chunk_rep.append(self.coord_dict[coord])
                            was_found = True
                            break
                if not was_found:
                    chunk_rep.append(-1)

        return chunk_rep

    def get_neighbouring_chunks(self, chunk, chunklist=None, con_mode=7):
        """ Returns the numbers of all neighbours

        Parameters:
        -----------
        cset: chunkDataset object
        chunk: chunk object

        Returns:
        --------
        list of int
            -1 if neighbour does not exist, else number
             order: [< x, < y, < z, > x, > y, > z]
        con_mode: int
            either 7, 19 or 27, defines which neighbours are considered
        """
        if chunklist is None:
            chunklist = self.chunklist
            if len(chunklist) == 0:
                chunklist = self.chunk_dict.keys()

        assert(con_mode in [7, 19, 27])

        stencil = np.ones([3, 3, 3], dtype=np.bool)
        stencil[1, 1, 1] = 0
        if con_mode != 27:
            for x in [0, 2]:
                for y in [0, 2]:
                    for z in [0, 2]:
                        stencil[x, y, z] = False

        if con_mode == 7:
            for x in range(3):
                for y in range(3):
                    for z in range(3):
                        if (x+y+z) % 2 == 1:
                            stencil[x, y, z] = False

        coordinate = np.array(chunk.coordinates)
        neighbours = []
        pos = []

        for x in range(3):
            for y in range(3):
                for z in range(3):
                    if stencil[x, y, z]:
                        this_coordinate = coordinate + chunk.size * \
                                                       np.array([x-1, y-1, z-1])

                        if tuple(this_coordinate) in self.coord_dict:
                            neighbour = self.coord_dict[tuple(this_coordinate)]
                            if neighbour in chunklist:
                                neighbours.append(neighbour)
                            else:
                                neighbours.append(-1)
                        else:
                            neighbours.append(-1)
                        pos.append([x-1, y-1, z-1])

        pos = np.array(pos)
        neighbours = np.array(neighbours)
        return neighbours, pos

    def from_chunky_to_matrix(self, size, offset, name, setnames,
                              dtype=np.uint32, outputpath=None,
                              binary=False,
                              interpolated_data=np.ones(3),
                              show_progress=False):
        interpolated_data = np.array(interpolated_data, dtype=np.int32)

        dataset_offset = np.array(self.box_coords, dtype=np.uint32)
        start = [knossosdataset.get_first_block(dim,
                                                np.array(
                                                    offset) - dataset_offset,
                                                self.chunk_size)
                 for dim in range(3)]
        end = [knossosdataset.get_last_block(dim, size,
                                             np.array(offset) - dataset_offset,
                                             self.chunk_size) + 1
               for dim in range(3)]

        output_matrix = {}
        for hdf5_name in setnames:
            output_matrix[hdf5_name] = np.zeros(
                (
                (end[0] - start[0]) * self.chunk_size[0] * interpolated_data[0],
                (end[1] - start[1]) * self.chunk_size[1] * interpolated_data[1],
                (end[2] - start[2]) * self.chunk_size[2] * interpolated_data[2]),
                dtype=dtype)

        offset_start = [(offset[dim] - dataset_offset[dim]) %
                        (self.chunk_size[dim] * interpolated_data[dim])
                        for dim in range(3)]

        offset_end = [(end[dim] - start[dim]) * self.chunk_size[dim] *
                      interpolated_data[dim] - offset_start[dim] -
                      size[dim] * interpolated_data[dim] for dim in range(3)]

        coord_dict = {}
        nb_chunks = len(self.chunk_dict)
        for nb_chunk in range(nb_chunks):
            coordinate = self.chunk_dict[nb_chunk].coordinates
            coord_dict[(coordinate[0], coordinate[1], coordinate[2])] = nb_chunk

        cnt = 0
        current = [start[dim] for dim in range(3)]
        nb_chunks_to_process = \
            (end[2] - start[2]) * (end[1] - start[1]) * (end[0] - start[0])

        while current[2] < end[2]:
            current[1] = start[1]
            while current[1] < end[1]:
                current[0] = start[0]
                while current[0] < end[0]:
                    if show_progress:
                        progress = 100 * cnt / float(nb_chunks_to_process)
                        sys.stdout.write('\rProgress: %.2f%%' % progress)
                        sys.stdout.flush()
                    values_dict = {}
                    current_coordinate = (current[0] * self.chunk_size[0] +
                                          dataset_offset[0],
                                          current[1] * self.chunk_size[1] +
                                          dataset_offset[1],
                                          current[2] * self.chunk_size[2] +
                                          dataset_offset[2])
                    try:
                        nb_current_chunk = coord_dict[current_coordinate]
                        path = self.path_head_folder + \
                               "/chunky_%d/%s.h5" % (nb_current_chunk, name)

                        f = h5py.File(path, 'r')
                        for hdf5_name in setnames:
                            values_dict[hdf5_name] = f[hdf5_name][()]
                        f.close()
                    except Exception as e:
                        print("Exception:", e)
                        for hdf5_name in setnames:
                            values_dict[hdf5_name] = np.zeros((
                                self.chunk_size[0] * interpolated_data[0],
                                self.chunk_size[1] * interpolated_data[1],
                                self.chunk_size[2] * interpolated_data[2]))
                        print("Cube does not exist, cube with zeros only assigned:", current_coordinate)

                    cnt += 1

                    sub = np.subtract(np.array(current), np.array(start)) * \
                          np.array(self.chunk_size) * interpolated_data

                    for hdf5_name in setnames:
                        values = np.copy(values_dict[hdf5_name])
                        values_dict[hdf5_name] = []
                        if binary:
                            values = np.array(values > 0, dtype=np.uint8)

                        offset = np.zeros(3, dtype=np.int32)
                        for dim in range(3):
                            if values.shape[dim] != self.chunk_size[dim] * interpolated_data[dim]:
                                offset[dim] = \
                                    int((values.shape[dim]-self.chunk_size[dim] *
                                        interpolated_data[dim])//2)
                        values = values[offset[0]: values.shape[0] - offset[0],
                                        offset[1]: values.shape[1] - offset[1],
                                        offset[2]: values.shape[2] - offset[2]]

                        offset = np.zeros(3, dtype=np.int32)
                        for dim in range(3):
                            if values.shape[dim] != self.chunk_size[dim] * \
                                    interpolated_data[dim]:
                                offset[dim] = \
                                    int(values.shape[dim] - self.chunk_size[
                                        dim] *
                                        interpolated_data[dim])
                        values = values[:values.shape[0] - offset[0],
                                 :values.shape[1] - offset[1],
                                 :values.shape[2] - offset[2]]

                        output_matrix[hdf5_name][
                        sub[0]: sub[0] + self.chunk_size[0] * interpolated_data[0],
                        sub[1]: sub[1] + self.chunk_size[1] * interpolated_data[1],
                        sub[2]: sub[2] + self.chunk_size[2] * interpolated_data[2]] \
                            = np.swapaxes(np.array(values).reshape(
                            self.chunk_size[0] * interpolated_data[0],
                            self.chunk_size[1] * interpolated_data[1],
                            self.chunk_size[2] * interpolated_data[2]), 0, 0)
                    current[0] += 1
                current[1] += 1
            current[2] += 1
        for hdf5_name in setnames:
            # cut_matrix cuts in ZYX order
            output_matrix[hdf5_name] = knossosdataset.cut_matrix(
                output_matrix[hdf5_name], offset_start[::-1], offset_end[::-1],
                (self.chunk_size * interpolated_data)[::-1], start[::-1], end[::-1])

        for this_key in output_matrix.keys():
            if False in [output_matrix[this_key].shape[dim] ==
                         np.array(size[dim])*interpolated_data[dim]
                         for dim in range(3)]:
                raise Exception("Incorrect shape! Should be", size, "; got:",
                                output_matrix[this_key].shape)
        else:
            pass

        if outputpath is not None:
            f = h5py.File(outputpath)
            for hdf5_name in setnames:
                f.create_dataset(hdf5_name, data=output_matrix[hdf5_name],
                                 compression="gzip")
            f.close()
        else:
            return output_matrix

    def from_matrix_to_chunky(self, offset, chunk_offset, data, name, h5_name,
                              datatype=None, verbose=True, n_threads=16):
        # TODO: untested with new ZYX order in knossosdataset.py
        def _write_chunks(args):
            path = args[0]
            h5_name = args[1]
            low = args[2]
            high = args[3]
            low_cut = args[4]
            high_cut = args[5]

            # print(low, high, low_cut, high_cut)
            chunk_data = {}
            if os.path.exists(path):
                with h5py.File(path, "r") as f:
                    for key in f.keys():
                        chunk_data[key] = f[key][()]

                    if not h5_name in f.keys():
                        chunk_data[h5_name] = np.zeros(
                            chunk_offset * 2 + self.chunk_size,
                            dtype=datatype)
                        if verbose:
                            print("Cube does not exist, cube with zeros "
                                  "only assigned")
            else:
                chunk_data[h5_name] = np.zeros(chunk_offset * 2 + self.chunk_size,
                                      dtype=datatype)

            chunk_data[h5_name][low[0]: high[0],
                                low[1]: high[1],
                                low[2]: high[2]] = \
                data[low_cut[0]: high_cut[0],
                     low_cut[1]: high_cut[1],
                     low_cut[2]: high_cut[2]]

            with h5py.File(path, "w") as f:
                for key in chunk_data.keys():
                    f.create_dataset(key, data=chunk_data[key],
                                     compression="gzip")

        if datatype is None:
            datatype = data.dtype

        chunk_offset = np.array(chunk_offset, dtype=np.int32)

        start = np.floor(np.array([(offset[dim] - chunk_offset[dim]) /
                                   float(self.chunk_size[dim])
                                   for dim in range(3)]))
        start = start.astype(np.int32)
        end = np.floor(np.array([(offset[dim] + chunk_offset[dim] + data.shape[dim] - 1) /
                                 float(self.chunk_size[dim]) for dim in range(3)]))
        end = end.astype(np.int32)

        current = np.copy(start)

        multithreading_params = []

        while current[2] <= end[2]:
            current[1] = start[1]
            while current[1] <= end[1]:
                current[0] = start[0]
                while current[0] <= end[0]:
                    chunk_coord = current * np.array(self.chunk_size)
                    if tuple(chunk_coord) in self.coord_dict:
                        chunk_id = self.coord_dict[tuple(chunk_coord)]

                        path = self.path_head_folder + \
                               "/chunky_%d/%s.h5" % (chunk_id, name)

                        low = np.array(offset - (chunk_coord - chunk_offset))
                        low_cut = low * (-1)
                        low[low < 0] = 0
                        low_cut[low_cut < 0] = 0

                        high = low + np.array(data.shape) - low_cut - \
                               self.chunk_size - 2 * chunk_offset
                        high = high.astype(np.int32)
                        high_cut = np.array(data.shape)
                        high_cut[high > 0] -= high[high > 0]
                        high[high > 0] = 0
                        high += self.chunk_size + 2 * chunk_offset

                        multithreading_params.append([path, h5_name, low, high,
                                                      low_cut, high_cut])

                    current[0] += 1
                current[1] += 1
            current[2] += 1

        if n_threads > 1:
            pool = ThreadPool(n_threads)
            pool.map(_write_chunks, multithreading_params)
            pool.close()
            pool.join()
        else:
            for params in multithreading_params:
                _write_chunks(params)

    def delete_all_cubes_by_name(self, fullname, nb_threads=10, folder=False):
        def _find_and_delete_cubes(file):
            if folder:
                os.rmdir(file)
                print(file)
            else:
                os.remove(file)

        glob_input = glob.glob(self.path_head_folder + "/chunky_*/" + fullname)
        params = glob_input

        pool = ThreadPool(nb_threads)
        pool.map(_find_and_delete_cubes, params)
        pool.close()
        pool.join()

    def export_cset_to_tiff_stack(self, save_path, name, hdf5names,
                                  nb_processes, z_stride, size):
        multi_params = []
        for step in range(int(np.ceil(size[2] / float(z_stride)))):
            multi_params.append([self, save_path, name, hdf5names,
                                 step * z_stride, z_stride, size])

        if nb_processes > 1:
            pool = Pool(nb_processes)
            pool.map(_export_cset_to_tiff_stack_thread, multi_params)
            pool.close()
        else:
            for params in multi_params:
                _export_cset_to_tiff_stack_thread(params)

    def export_cset_to_kd(self, kd, name, hdf5names, nb_threads,
                          coordinate=None, size=None,
                          stride=[4 * 128, 4 * 128, 4 * 128],
                          as_raw=False, fast_downsampling=False,
                          unified_labels=False, orig_dtype=np.uint8,
                          target_mags=None):
        if coordinate is None or size is None:
            coordinate = np.zeros(3, dtype=np.int32)
            size = np.copy(kd.boundary)

        multi_params = []
        for coordx in range(coordinate[0], coordinate[0] + size[0],
                            stride[0]):
            for coordy in range(coordinate[1], coordinate[1] + size[1],
                                stride[1]):
                for coordz in range(coordinate[2], coordinate[2] + size[2],
                                    stride[2]):
                    coords = np.array([coordx, coordy, coordz])
                    multi_params.append([coords, stride, self.path_head_folder,
                                         kd.knossos_path, name, hdf5names, as_raw,
                                         unified_labels, nb_threads[1], orig_dtype,
                                         fast_downsampling, target_mags])

        np.random.shuffle(multi_params)
        if nb_threads[0] > 1:
            pool = Pool(processes=nb_threads[0])
            pool.map(_export_cset_as_kd_thread, multi_params)
            pool.close()
            pool.join()
        else:
            for params in multi_params:
                _export_cset_as_kd_thread(params)

        if nb_threads[0] > 1:
            pool = Pool(processes=nb_threads[0])
            pool.map(_export_cset_as_kd_control_thread, multi_params)
            pool.close()
            pool.join()
        else:
            for params in multi_params:
                _export_cset_as_kd_control_thread(params)


class Chunk(object):
    """ Virtual chunk which gets real when calling its data directly

    Parameters:
    -----------
    coordinates: 3 sequence of int
        defines the coordinates of the chunk without overlap
    size: 3 sequence of int
        defines the size of the chunk without overlap
    number: int
        number(=key) of the chunk in the dictionary of chunkDataset
    dataset: eg. knossosDataset()
        defines the dataset where the data is taken from
    overlap: 3 sequence of int
        defines the overlap of the chunk
    for_cnn: boolean
        uses a specific offset at the edges of x and y
        to account for the border problem of CNN prediction
    """

    def __init__(self):
        self.coordinates = np.zeros(3)
        self.size = np.zeros(3)
        self.number = None
        self._dataset_path = ""
        self.overlap = np.zeros(3)
        self.path_head_folder = None
        self.folder = None
        self.box_size = None
        self.feature_file = ''
        self._dataset = None

    @property
    def dataset(self):
        if self._dataset is None:
            assert os.path.exists(self._dataset_path)
            kd = knossosdataset.KnossosDataset()
            kd.initialize_from_conf(self._dataset_path)
        else:
            kd = self._dataset
        return kd

    def raw_data(self, zyx_mode=False, overlap=None, invert_raw=False):
        """ Uses DatasetUtils.knossosDataset for getting the real data

        Parameters:
        -----------
        zyx_mode: bool
            If True, data is returned as ZYX.
        overlap: 3 sequence of int
            defines overlap of extracted data
        invert_raw: bool

        Returns:
        --------

        raw data of the chunk
        """

        if overlap is None:
            overlap = self.overlap

        size = np.array(np.array(self.size) + 2 * np.array(overlap),
                        dtype=np.int32)
        coords = np.array(np.array(self.coordinates) -
                          np.array(overlap), dtype=np.int32)
        data = self.dataset.load_raw(offset=coords, size=size,
                                     mag=1, padding=0)
        if invert_raw:
            data = np.invert(data)
        if not zyx_mode:
            data = data.swapaxes(0, 2)
        return data

    def seg_data(self, zyx_mode=False, with_overlap=False, dtype_opt=np.uint64,
                 invert_seg=False):
        """ Uses DatasetUtils.knossosDataset for getting the seg data

        Parameters:
        -----------
        zyx_mode: bool
            If True, data is returned as zyx.
        with_overlap: bool
        dtype_opt:

        Returns:
        --------

        seg data of the chunk
        """
        if with_overlap:
            size = np.array(np.array(self.size) + 2 * np.array(self.overlap),
                            dtype=np.int32)
            coords = np.array(
                np.array(self.coordinates) - np.array(self.overlap),
                dtype=np.int32)
        else:
            size = np.array(np.array(self.size),
                            dtype=np.int32)
            coords = np.array(np.array(self.coordinates),
                              dtype=np.int32)
        data = self.dataset.load_seg(offset=coords, size=size, mag=1, padding=0,
                                     datatype=dtype_opt)
        if invert_seg:
            data = np.invert(data)
        if not zyx_mode:
            data = data.swapaxes(0, 2)
        return data

    def write_overlaycube(self, seg_name=None, seg_set_name=None,
                          swap_axes=0, without_overlap=True,
                          labels_data=None, overwrite=True,
                          write_pathlist=False, mag=[1, 2, 4, 8],
                          as_zip=False, output_zipname=''):

        """writes segmentation data to knossos dataset in form of overlaycubes

        Parameters:
        __________

        seg_name: str
            name of segmentation file
        seg_set_name: str
            name of set name of hdf5 file
        without_overlap: logical
            if set to False, the overlap of the corresponding chunk is
            also written to the dataset
        labels_data: numpy array
            segmentation data is either given by indicating the hdf5 name (->seg_name)

        """

        if labels_data is None:
            labels_data = self.load_chunk(seg_name, seg_set_name)
        coord = self.coordinates - self.overlap

        if without_overlap:
            labels_data = labels_data[self.overlap[0]:-self.overlap[0],
                          self.overlap[1]:-self.overlap[1],
                          self.overlap[2]:-self.overlap[2]]
            coord = self.coordinates
        if swap_axes:
            raise NotImplementedError
        if not write_pathlist:
            self.dataset.from_matrix_to_cubes(coord, data=[labels_data],
                                              verbose=False, overwrite=overwrite,
                                              mags=mag, kzip_path=output_zipname)
        else:
            raise NotImplementedError
            path_list = self.dataset.from_matrix_to_overlaycubes(coord,
                                                                 labels_data=[
                                                                     labels_data],
                                                                 swapaxes_option=swap_axes,
                                                                 verbose=True,
                                                                 overwrite=overwrite,
                                                                 write_pathlist=True,
                                                                 mags=mag,
                                                                 as_zip=as_zip,
                                                                 output_zipname=output_zipname)
            return path_list

    def save_chunk(self, data, name, setname, compress=True, overwrite=False):

        """save chunk creates folder structure where chunks are saved by number
        different filetype can be saved in one HDF5 file. Cannot override

        Parameters:
        __________

        data: numpy array
            data wished to be saved
        chunk_number: int
            number of chunk from calculate_chunks
        path_head_folder: str
            path of 12ead_folder for data_structure
        name: str whithout the .h5 or h5py, will be saved as h5
            name of HDF5 file
        setname: str
            name of set in HDF5 file
        overwrite: logical
            if set True, existing HDF5 file is overwritten
        """
        path = self.folder + name + '.h5'
        if not os.path.exists(self.path_head_folder):
            os.makedirs(self.path_head_folder)

        if not os.path.exists(self.folder):
            os.makedirs(self.folder)

        if overwrite:
            try:
                f = h5py.File(path, 'w')
            except:
                os.remove(path)
                f = h5py.File(path, 'w')
        else:
            f = h5py.File(path, 'a')
        if type(setname) == list or type(setname) == np.ndarray:
            for nb_data in range(len(data)):
                if compress:
                    f.create_dataset(str(setname[nb_data]), data=data[nb_data],
                                     compression="gzip")
                else:
                    f.create_dataset(str(setname[nb_data]), data=data[nb_data])
        else:
            if compress:
                f.create_dataset(str(setname), data=data, compression="gzip")
            else:
                f.create_dataset(str(setname), data=data)
        f.close()

    def load_chunk(self, name, setname=None, verbose=False):

        """ returns data from set in HDF5_file

        Parameters
        ---------

        path_head_folder: string
            path to head folder with / at the end
        chunk_number: int
            chunk_number from chunkDataset
        name:
            name of HDF5 file
        setname:
            name of set in the HDF5 file
        """
        if type(name) != str:
            name = str(name)
        path = self.folder + name + '.h5'

        if not os.path.exists(self.path_head_folder):
            print(self.path_head_folder)
            raise Exception('path_head_folder to correct, check "/" at the end')
        if not os.path.exists(self.folder):
            print(self.folder)
            raise Exception('chunky folder does not exist')
        if verbose:
            print('loading:', path)

        f = h5py.File(path, 'r')
        if verbose:
            print('file has following setnames:', list(f.keys()))
            print('setname(s)', setname)
        if setname is None:
            setname = list(f.keys())

        if type(setname) == list or type(setname) == np.ndarray:
            data = []
            for this_setname in setname:
                data.append(f[this_setname][()])
        else:
            data = f[setname][()]
        f.close()

        return data


class FSLock(object):
    def __init__(self, path):
        self.path = path
        self.f = None
        self.is_acquired = False

    def acquire(self):
        try:
            self.f = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_RDWR)
            time.sleep(.5)
            self.is_acquired = True
            os.close(self.f)
            return True
        except:
            return False

    def release(self):
        self.is_acquired = False

    def __del__(self):
        self.release()


class ChunkDistributor(object):
    def __init__(self, cset, name, chunklist=None, start_chunk=None):
        self.cset = cset
        self.exp_name = name
        self.status_name = ["running", "writing", "done"]

        if chunklist is not None:
            self.chunklist = chunklist
        else:
            self.chunklist = list(range(len(self.cset.chunk_dict)))

        if start_chunk is None:
            self.next_id = np.random.randint(0, len(self.chunklist))
        else:
            self.next_id = start_chunk

        self.lock = None
        self.status = dict.fromkeys(self.chunklist, False)

    def next(self, exclude_running=True):
        if self.lock is not None:
            self.lock.release()

        for _ in range(2 * len(self.chunklist)):
            if not os.path.exists(self._path_lock(self.next_id, status=3)):
                running = os.path.exists(self._path_lock(self.next_id, status=1))
                if exclude_running and running: # need to remove otherwise acquire fails
                    self._increase_id()
                    continue
                elif running:
                    os.remove(self._path_lock(self.next_id, status=1))

                self.lock = FSLock(self._path_lock(self.next_id, status=1))
                if self.lock.acquire():
                    return self.cset.chunk_dict[self.next_id]

            self._increase_id()

        print("No chunks left")
        self.get_status()
        return None

    def get_write(self):
        if self.lock is not None:
            self.lock.release()

        self.lock = FSLock(self._path_lock(self.next_id, status=2))

        if self.lock.acquire():
            return True
        else:
            return False

    def sign_done(self):
        if self.lock is not None:
            self.lock.release()

        self.lock = FSLock(self._path_lock(self.next_id, status=3))
        self.lock.acquire()
        self.lock.release()

    def clean_locks(self, status=None):
        if status is None:
            paths = glob.glob(self.cset.path_head_folder + "/chunky_*/*.lock")
        else:
            paths = glob.glob(self._path_lock("*", status=status))

        for path in paths:
            os.remove(path)

    def get_status(self):
        for status in [1, 2, 3]:
            n_locks = len(glob.glob(self._path_lock("*", status=status)))
            print("%d of %d are %s" % (n_locks, len(self.chunklist),
                                       self.status_name[status-1]))

    def _path_lock(self, chunk_id, status=1):
        base_path = self.cset.path_head_folder + "/chunky_%s/" % str(chunk_id)
        return base_path + "/%s_%s.lock" % (self.exp_name,
                                            self.status_name[status-1])

    def _increase_id(self):
        self.next_id += 1
        self.next_id %= len(self.chunklist)
