#emacs: -*- mode: python-mode; py-indent-offset: 4; indent-tabs-mode: nil -*-
#ex: set sts=4 ts=4 sw=4 et:
### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the PyMVPA package for the
#   copyright and license terms.
#
### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Dataset container

TODO!! marks specific TODO items adherent to Dataset becoming a kid of ndarray
"""

__docformat__ = 'restructuredtext'

import operator
import random
import copy as copylib

import numpy as N

from mvpa.misc.exceptions import DatasetError

if __debug__:
    from mvpa.misc import debug, warning

class Dataset(N.ndarray):
    """This class provides a container to store all necessary data to perform
    MVPA analyses. These are the data samples, as well as the labels
    associated with these patterns. Additionally samples can be grouped into
    chunks.

    :Groups:
      - `Creators`: `__init__`, `selectFeatures`, `selectSamples`, `applyMapper`
      - `Mutators`: `permuteLabels`

    Important: labels assumed to be immutable, ie noone should modify
    them externally by accessing indexed items, ie something like
    ``dataset.labels[1] += "_bad"`` should not be used. If a label has
    to be modified, full copy of labels should be obtained, operated
    on, and assigned back to the dataset, otherwise
    dataset.labels would not work.  The same applies to any
    other attribute which has corresponding unique* access property.
    """

    # static definition to track which unique attributes
    # have to be reset/recomputed whenever anything relevant
    # changes

    # unique{labels,chunks} become a part of dsattr
    _uniqueattributes = []
    """Unique attributes associated with the data"""

    _registeredattributes = []
    """Registered attributes (stored in _data)"""

    _requiredattributes = ['samples', 'labels']
    """Attributes which have to be provided to __init__, or otherwise
    no default values would be assumed and construction of the
    instance would fail"""

    def __new__(cls, samples=None, dtype=None, copy=True,
                data=None, dsattr=None, labels=None, chunks=None,
                check_data=True, copy_data=False, copy_dsattr=True):

        # XXX N.array has also following args of the call so...
        #
        #  order  - Specify the order of the array.  If order is 'C', then the
        #            array will be in C-contiguous order (last-index varies the
        #            fastest).  If order is 'FORTRAN', then the returned array
        #            will be in Fortran-contiguous order (first-index varies the
        #            fastest).  If order is None, then the returned array may
        #            be in either C-, or Fortran-contiguous order or even
        #            discontiguous.
        #  subok  - If True, then sub-classes will be passed-through, otherwise
        #            the returned array will be forced to be a base-class array
        #  ndmin  - Specifies the minimum number of dimensions that the resulting
        #            array should have.  1's will be pre-pended to the shape as
        #            needed to meet this requirement.

        """Initialize dataset instance

        TODO!! : adjust according ^^^

        :Parameters:
          data : dict
            Dictionary with an arbitrary number of entries. The value for
            each key in the dict has to be an ndarray with the
            same length as the number of rows in the samples array.
            A special entry in theis dictionary is 'samples', a 2d array
            (samples x features). A shallow copy is stored in the object.
          dsattr : dict
            Dictionary of dataset attributes. An arbitrary number of
            arbitrarily named and typed objects can be stored here. A
            shallow copy of the dictionary is stored in the object.
          dtype
            If None -- do not change data type if samples
            is an ndarray. Otherwise convert samples to dtype.

        :Keywords:
          samples : ndarray
            a 2d array (samples x features)
          labels
            array or scalar value defining labels for each samples
          chunks
            array or scalar value defining chunks for each sample

        Each of the Keywords arguments overwrites what is/might be
        already in the `data` container.

        """

        # see if data and dsattr are none, if so, make them empty dicts
        if data is None:
            data = {}
        if dsattr is None:
            dsattr = {}

        # initialize containers; default values are empty dicts
        # always make a shallow copy of what comes in, otherwise total chaos
        # is likely to happen soon
        if copy_data:
            # deep copy (cannot use copylib.deepcopy, because samples is an
            # exception
            # but shallow copy first to get a shared version of the data in
            # any case
            _data = data.copy()
            for k, v in data.iteritems():
                # skip copying samples if requested
                if k == 'samples' and not copy:
                    continue
                _data[k] = v.copy()
        else:
            # shallow copy
            # XXX? yoh: it might be better speed wise just assign dictionary
            #      without any shallow .copy
            _data = data.copy()

        if copy_dsattr and len(dsattr)>0:
            # deep copy
            if __debug__:
                debug('DS', "Deep copying dsattr %s" % `dsattr`)
            _dsattr = copylib.deepcopy(dsattr)

        else:
            # shallow copy
            _dsattr = copylib.copy(dsattr)

        # store samples (and possibly transform/reshape/retype them)
        if not samples == None:
            if __debug__:
                if _data.has_key('samples'):
                    debug('DS',
                          "`Data` dict has `samples` (%s) but there is also" +
                          " __init__ parameter `samples` which overrides " +
                          " stored in `data`" % (`_data['samples'].shape`))
            if __debug__:
                debug('DS', "Assigning samples")
            _data['samples'] = Dataset._shapeSamples(samples, dtype,
                                                     copy)

        if _data.has_key('samples'):
            # we have done everything correct so far ;-)
            nsamples = _data['samples'].shape[0]
        else:
            raise DatasetError, "No samples data was provided"

        # TODO? we might want to have the same logic for chunks and labels
        #       ie if no labels present -- assign arange
        # labels
        if not labels == None:
            if __debug__:
                if _data.has_key('labels'):
                    debug('DS',
                          "`Data` dict has `labels` (%s) but there is also" +
                          " __init__ parameter `labels` which overrides " +
                          " stored in `data`" % (`_data['labels']`))
            if _data.has_key('samples'):
                _data['labels'] = \
                    Dataset._expandSampleAttribute(nsamples, labels, 'labels')

        # check if we got all required attributes
        for attr in Dataset._requiredattributes:
            if not _data.has_key(attr):
                raise DatasetError, \
                      "Attribute %s is required to initialize dataset" % \
                      attr

        # chunks
        if not chunks == None:
            _data['chunks'] = \
                Dataset._expandSampleAttribute(nsamples, chunks, 'chunks')
        elif not _data.has_key('chunks'):
            # if no chunk information is given assume that every pattern
            # is its own chunk
            _data['chunks'] = N.arange(nsamples)

        # Initialize attributes which are registered but were not setup
        for attr in Dataset._registeredattributes:
            if not _data.has_key(attr):
                if __debug__:
                    debug("DS", "Initializing attribute %s" % attr)
                _data[attr] = N.zeros(nsamples)

        # lazy computation of unique members
        #self._resetallunique('_dsattr', self._dsattr)

        # Michael: we cannot do this conditional here. When selectSamples()
        # removes a whole data chunk the uniquechunks values will be invalid.
        # Same applies to labels of course.
        if not labels is None or not chunks is None:
            # for a speed up to don't go through all uniqueattributes
            # when no need
            _dsattr['__uniquereseted'] = False
            # TODO!!?? reset in __array_finalize__
            #_resetallunique(force=True)

        ###### prepare numpy.ndarray
        # pop out 'samples' and make them THE object for now
        result = N.array(_data.pop('samples'))
        result = result.view(cls)
        setattr(result, '_data', _data)
        setattr(result, '_dsattr', _dsattr)
        result._resetallunique(force=True)

        # TODO!!: enable checkup of _data
        if check_data:
            result._checkData()
        return result


    def __array_finalize__(self, obj):
        """Copy Dataset's _data and _dsattr."""
        ## TODO!! Think about deepcopying!
        for tag in ['_data', '_dsattr']:
            setattr(self, tag, copylib.copy(getattr(obj, tag, None)))
        return

    @property
    def _id(self):
        """To verify if dataset is in the same state as when smth else was done

        Like if classifier was trained on the same dataset as in question"""

        res = id(self._data) + hash(buffer(self))
        for val in self._data.values():
            res += id(val)
            if isinstance(val, N.ndarray):
                res += hash(buffer(val))
        return res


    def _resetallunique(self, force=False):
        """Set to None all unique* attributes of corresponding dictionary
        """

        if not force and self._dsattr['__uniquereseted']:
            return

        # I guess we better checked if dictname is known  but...
        for k in self._uniqueattributes:
            if __debug__:
                debug("DS", "Reset attribute %s" % k)
            self._dsattr[k] = None
        self._dsattr['__uniquereseted'] = True


    def _getuniqueattr(self, attrib, dict_):
        """Provide common facility to return unique attributes

        XXX `dict_` can be simply replaced now with self._dsattr
        """
        if not self._dsattr.has_key(attrib) or self._dsattr[attrib] is None:
            if __debug__:
                debug("DS", "Recomputing unique set for attrib %s within %s" %
                      (attrib, self.__repr__(False)))
            # uff... might come up with better strategy to keep relevant
            # attribute name
            self._dsattr[attrib] = N.unique( dict_[attrib[6:]] )
            assert(not self._dsattr[attrib] is None)
            self._dsattr['__uniquereseted'] = False

        return self._dsattr[attrib]


    def _setdataattr(self, attrib, value):
        """Provide common facility to set attributes

        """
        if len(value) != self.nsamples:
            raise ValueError, \
                  "Provided %s have %d entries while there is %d samples" % \
                  (attrib, len(value), self.nsamples)
        self._data[attrib] = N.array(value)
        uniqueattr = "unique" + attrib

        if self._dsattr.has_key(uniqueattr):
            self._dsattr[uniqueattr] = None


    def _getNSamplesPerAttr( self, attrib='labels' ):
        """Returns the number of samples per unique label.
        """
        # XXX hardcoded dict_=self._data.... might be in self._dsattr
        uniqueattr = self._getuniqueattr(attrib="unique" + attrib,
                                         dict_=self._data)

        # use dictionary to cope with arbitrary labels
        result = dict(zip(uniqueattr, [ 0 ] * len(uniqueattr)))
        for l in self._data[attrib]:
            result[l] += 1

        # XXX only return values to mimic the old interface but we might want
        # to return the full dict instead
        # return result
        return result




    def _getSampleIdsByAttr(self, values, attrib="labels"):
        """Return indecies of samples given a list of attributes
        """

        if not operator.isSequenceType(values):
            values = [ values ]

        # TODO: compare to plain for loop through the labels
        #       on a real data example
        sel = N.array([], dtype=N.int16)
        for value in values:
            sel = N.concatenate((
                sel, N.where(self._data[attrib]==value)[0]))

        # place samples in the right order
        sel.sort()

        return sel

    @staticmethod
    def _shapeSamples(samples, dtype, copy):
        """Adapt different kinds of samples

        Handle all possible input value for 'samples' and tranform
        them into a 2d (samples x feature) representation.
        """
        # put samples array into correct shape
        # 1d arrays or simple sequences are assumed to be a single pattern
        if (not isinstance(samples, N.ndarray)):
            # it is safe to provide dtype which defaults to None,
            # when N would choose appropriate dtype automagically
            samples = N.array(samples, ndmin=2, dtype=dtype, copy=copy)
        else:
            if samples.ndim < 2 \
                   or (not dtype is None and dtype != samples.dtype):
                if dtype is None:
                    dtype = samples.dtype
                samples = N.array(samples, ndmin=2, dtype=dtype, copy=copy)
            elif copy:
                samples = samples.copy()

        # only samples x features matrices are supported
        if len(samples.shape) > 2:
            raise DatasetError, "Only (samples x features) -> 2d sample " \
                            + "are supported (got %s shape of samples)." \
                            % (`samples.shape`) \
                            +" Consider MappedDataset if applicable."

        return samples


    def _checkData(self):
        """Checks `_data` members to have the same # of samples.
        """
        for k, v in self._data.iteritems():
            if not len(v) == self.nsamples:
                raise DatasetError, \
                      "Length of sample attribute '%s' [%i] does not " \
                      "match the number of samples in the dataset [%i]." \
                      % (k, len(v), self.nsamples)


    @staticmethod
    def _expandSampleAttribute(nsamples, attr, attr_name):
        """If a sample attribute is given as a scalar expand/repeat it to a
        length matching the number of samples in the dataset.
        """
        try:
            if len(attr) != nsamples:
                raise DatasetError, \
                      "Length of sample attribute '%s' [%d]" \
                      % (attr_name, len(attr)) \
                      + " has to match the number of samples" \
                      + " [%d]." % nsamples
            # store the sequence as array
            return N.array(attr)

        except TypeError:
            # make sequence of identical value matching the number of
            # samples
            return N.repeat(attr, nsamples)


    @classmethod
    def _registerAttribute(cls, key, dictname="_data", hasunique=False,
                           default_setter=True):
        """Register an attribute for any Dataset class.

        Creates property assigning getters/setters depending on the
        availability of corresponding _get, _set functions.
        """
        #import pydb
        #pydb.debugger()
        classdict = cls.__dict__
        if not classdict.has_key(key):
            if __debug__:
                debug("DS", "Registering new attribute %s" % key)
            # define get function and use corresponding
            # _getATTR if such defined
            getter = '_get%s' % key
            if classdict.has_key(getter):
                getter =  '%s.%s' % (cls.__name__, getter)
            else:
                getter = "lambda x: x.%s['%s']" % (dictname, key)

            # define set function and use corresponding
            # _setATTR if such defined
            setter = '_set%s' % key
            if classdict.has_key(setter):
                setter =  '%s.%s' % (cls.__name__, setter)
            elif default_setter and dictname=="_data":
                setter = "lambda self,x: self._setdataattr" + \
                         "(attrib='%s', value=x)" % (key)
            else:
                setter = None

            if __debug__:
                debug("DS", "Registering new property %s.%s" %
                      (cls.__name__, key))
            exec "%s.%s = property(fget=%s, fset=%s)"  % \
                 (cls.__name__, key, getter, setter)

            if hasunique:
                uniquekey = "unique%s" % key
                getter = '_get%s' % uniquekey
                if classdict.has_key(getter):
                    getter = '%s.%s' % (cls.__name__, getter)
                else:
                    getter = "lambda x: x._getuniqueattr" + \
                            "(attrib='%s', dict_=x.%s)" % (uniquekey, dictname)

                if __debug__:
                    debug("DS", "Registering new property %s.%s" %
                          (cls.__name__, uniquekey))

                exec "%s.%s = property(fget=%s)" % \
                     (cls.__name__, uniquekey, getter)

                # create samplesper<ATTR> properties
                sampleskey = "samplesper%s" % key[:-1] # remove ending 's' XXX
                if __debug__:
                    debug("DS", "Registering new property %s.%s" %
                          (cls.__name__, sampleskey))

                exec "%s.%s = property(fget=%s)" % \
                     (cls.__name__, sampleskey,
                      "lambda x: x._getNSamplesPerAttr(attrib='%s')" % key)

                cls._uniqueattributes.append(uniquekey)

                # create idsby<ATTR> properties
                sampleskey = "idsby%s" % key # remove ending 's' XXX
                if __debug__:
                    debug("DS", "Registering new property %s.%s" %
                          (cls.__name__, sampleskey))

                exec "%s.%s = %s" % (cls.__name__, sampleskey,
                      "lambda self, x: " +
                      "self._getSampleIdsByAttr(x,attrib='%s')" % key)

                cls._uniqueattributes.append(uniquekey)

            cls._registeredattributes.append(key)
        elif __debug__:
            warning('Trying to reregister attribute `%s`. For now ' % key +
                    'such capability is not present')


    def __repr__(self, full=True):
        """String summary over the object
        """
        s = """<Dataset / %s %d x %d""" % \
                   (self.dtype, self.nsamples, self.nfeatures)

        if not full:
            return s                    # enough is enough

        s +=  " uniq:"
        for uattr in self._dsattr.keys():
            if not uattr.startswith("unique"):
                continue
            attr = uattr[6:]
            try:
                value = self._getuniqueattr(attrib=uattr,
                                            dict_=self._data)
                s += " %d %s" % (len(value), attr)
            except:
                pass
        return s + '>'


    def __iadd__(self, other):
        """Merge the samples of one Dataset object to another (in-place).

        No dataset attributes will be merged!
        """
        if isinstance(other, Dataset):
            if not self.nfeatures == other.nfeatures:
                raise DatasetError, "Cannot add Dataset, because the number of " \
                                    "feature do not match."

            # if we deal with Datasets, we do our own semantics here
            out = N.concatenate( (self, other) )
            out = out.view(self.__class__)

            _data = {}
            # concatenate all sample attributes
            for k, v in self._data.iteritems():
                _data[k] = N.concatenate((v, other._data[k]), axis=0)

            setattr(out, '_data', _data)
            setattr(out, '_dsattr', self._dsattr)
            # might be more sophisticated but for now just reset -- it is safer ;)
            out._resetallunique()
            self = out
        else:
            # just  call ndarray's iadd
            self = super(Dataset, self).__iadd__(other)

        return self


    def __add__( self, other ):
        """Merge the samples two Dataset objects.

        All data of both datasets is copied, concatenated and a new Dataset is
        returned.

        NOTE: This can be a costly operation (both memory and time). If
        performance is important consider the '+=' operator.
        """

        # create a new object as a copy of current
        out = self.copy()
        out += other
        return out


    def selectFeatures(self, ids, sort=True):
        """Select a number of features from the current set.

        :Parameters:
          ids
            iterable container to select ids
          sort : bool
            if to sort Ids. Order matters and `selectFeatures` assumes
            incremental order. If not such, in non-optimized code
            selectFeatures would verify the order and sort

        Returns a new Dataset object with a view of the original
        samples array (no copying is performed).

        WARNING: The order of ids determines the order of features in
        the returned dataset. This might be useful sometimes, but can
        also cause major headaches! Order would is verified when
        running in non-optimized code (if __debug__)
        """
        # XXX set sort default to True, now sorting has to be explicitely
        # disabled and warning is not necessary anymore
        if sort:
            ids.sort()
#        elif __debug__:
#            from mvpa.misc.support import isSorted
#            if not isSorted(ids):
#                warning("IDs for selectFeatures must be provided " +
#                       "in sorted order, otherwise major headache might occur")

        # shallow-copy all stuff from current data dict
        new_data = self._data.copy()

        dataset = self[:, ids]
        dataset._data = new_data
        dataset._resetallunique()

        return dataset

        # TODO!!: check below code and wipe it out if indeed not needed
        # assign the selected features -- data is still shared with
        # current dataset
        new_data['samples'] = self[:, ids]

        # create a new object of the same type it is now and NOT only Dataset
        dataset = super(Dataset, self).__new__(self.__class__)

        # now init it: to make it work all Dataset contructors have to accept
        # Class(data=Dict, dsattr=Dict)
        dataset.__init__(data=new_data,
                         dsattr=self._dsattr,
                         check_data=False,
                         copy_samples=False,
                         copy=False,
                         copy_dsattr=False
                         )

        return dataset


    def applyMapper(self, featuresmapper=None, samplesmapper=None):
        """Obtain new dataset by applying mappers over features and/or samples.

        :Parameters:
          featuresmapper : Mapper
            `Mapper` to somehow transform each sample's features
          samplesmapper : Mapper
            `Mapper` to transform each feature across samples

        WARNING: At the moment, handling of samplesmapper is not yet
        implemented since there were no real use case.

        TODO: selectFeatures is pretty much applyMapper(featuresmapper=MaskMapper(...))
        """

        # shallow-copy all stuff from current data dict
        new_data = self._data.copy()

        # apply mappers

        if samplesmapper:
            raise NotImplementedError

        if featuresmapper:
            if __debug__:
                debug("DS", "Applying featuresmapper %s" % `featuresmapper` +
                      " to samples of dataset `%s`" % `self`)
            dataset = featuresmapper.forward(self)

        dataset._data = new_data
        dataset._resetallunique()

        return dataset

        # TODO!! check below
        # create a new object of the same type it is now and NOT only Dataset
        dataset = super(Dataset, self).__new__(self.__class__)

        # now init it: to make it work all Dataset contructors have to accept
        # Class(data=Dict, dsattr=Dict)
        dataset.__init__(samples=new_data,
                         data=new_data,
                         dsattr=self._dsattr,
                         check_data=False,
                         copy_samples=False,
                         copy=False,
                         copy_dsattr=False
                         )

        return dataset


    def selectSamples(self, mask):
        """Choose a subset of samples.

        Returns a new dataset object containing the selected sample
        subset.

        TODO: yoh, we might need to sort the mask if the mask is a
        list of ids and is not ordered. Clarify with Michael what is
        our intent here!
        """
        # without having a sequence a index the masked sample array would
        # loose its 2d layout
        if not operator.isSequenceType( mask ):
            mask = [mask]
        # TODO: Reconsider crafting a slice if it can be done to don't copy
        #       the data
        #try:
        #    minmask = min(mask)
        #    maxmask = max(mask)
        #except:
        #    minmask = min(map(int,mask))
        #    maxmask = max(map(int,mask))
        # lets see if we could get it done with cheap view/slice
        #(minmask, maxmask) != (0, 1) and \
        #if len(mask) > 2 and \
        #       N.array([N.arange(minmask, maxmask+1) == N.array(mask)]).all():
        #    slice_ = slice(minmask, maxmask+1)
        #    if __debug__:
        #        debug("DS", "We can and do convert mask %s into splice %s" %
        #              (mask, slice_))
        #    mask = slice_
        # mask all sample attributes
        data = {}
        for k, v in self._data.iteritems():
            data[k] = v[mask, ]

        # TODO!! we might need to copy explicitely here since mask can be a slice, thus...
        dataset = self[mask, ]
        dataset._data = data
        # TODO!! ??? is it needed below actually???
        #dataset._dsattr = copylib.copy(self._dsattr)
        dataset._resetallunique(force=True)
        return dataset

        #TODO!! check code below and remove
        # create a new object of the same type it is now and NOT onyl Dataset
        dataset = super(Dataset, self).__new__(self.__class__)

        # now init it: to make it work all Dataset contructors have to accept
        # Class(data=Dict, dsattr=Dict)
        dataset.__init__(data=data,
                         dsattr=self._dsattr,
                         check_data=False,
                         copy_samples=False,
                         copy=False,
                         copy_dsattr=False)


        return dataset



    def permuteLabels(self, status, perchunk = True):
        """Permute the labels.

        Calling this method with 'status' set to True, the labels are
        permuted among all samples.

        If 'perorigin' is True permutation is limited to samples sharing the
        same chunk value. Therefore only the association of a certain sample
        with a label is permuted while keeping the absolute number of
        occurences of each label value within a certain chunk constant.

        If 'status' is False the original labels are restored.
        """
        if not status:
            # restore originals
            if self._data['origlabels'] == None:
                raise RuntimeError, 'Cannot restore labels. ' \
                                    'permuteLabels() has never been ' \
                                    'called with status == True.'
            self.labels = self._data['origlabels']
            self._data['origlabels'] = None
        else:
            # store orig labels, but only if not yet done, otherwise multiple
            # calls with status == True will destroy the original labels
            if not self._data.has_key('origlabels') \
                or self._data['origlabels'] == None:
                # rebind old labels to origlabels
                self._data['origlabels'] = self._data['labels']
                # assign a copy so modifications do not impact original data
                self._data['labels'] = self._data['labels'].copy()

            # now scramble the rest
            if perchunk:
                for o in self.uniquechunks:
                    self._data['labels'][self.chunks == o ] = \
                        N.random.permutation( self.labels[ self.chunks == o ] )
                # to recompute uniquelabels
                self.labels = self._data['labels']
            else:
                self.labels = N.random.permutation(self._data['labels'])


    def getRandomSamples( self, nperlabel ):
        """Select a random set of samples.

        If 'nperlabel' is an integer value, the specified number of samples is
        randomly choosen from the group of samples sharing a unique label
        value ( total number of selected samples: nperlabel x len(uniquelabels).

        If 'nperlabel' is a list which's length has to match the number of
        unique label values. In this case 'nperlabel' specifies the number of
        samples that shall be selected from the samples with the corresponding
        label.

        The method returns a Dataset object containing the selected
        samples.
        """
        # if interger is given take this value for all classes
        if isinstance(nperlabel, int):
            nperlabel = [ nperlabel for i in self.uniquelabels ]

        sample = []
        # for each available class
        for i, r in enumerate(self.uniquelabels):
            # get the list of pattern ids for this class
            sample += random.sample( (self.labels == r).nonzero()[0],
                                     nperlabel[i] )

        return self.selectSamples( sample )


#    def _setchunks(self, chunks):
#        """Sets chunks and recomputes uniquechunks
#        """
#        self._data['chunks'] = N.array(chunks)
#        self._dsattr['uniquechunks'] = None # None!since we might not need them


    def getNSamples( self ):
        """Currently available number of patterns.
        """
        return self.shape[0]


    def getNFeatures( self ):
        """Number of features per pattern.
        """
        return self.shape[1]



    def setSamplesDType(self, dtype):
        """Set the data type of the samples array.
        """
        # change the underlying datatype
        if self.dtype != dtype:
            self = self.astype(dtype)


    def convertFeatureIds2FeatureMask(self, ids):
        """Returns a boolean mask with all features in `ids` selected.

        :Parameters:
            ids: list or 1d array
                To be selected features ids.

        :Returns:
            ndarray: dtype='bool'
                All selected features are set to True; False otherwise.
        """
        fmask = N.repeat(False, self.nfeatures)
        fmask[ids] = True

        return fmask


    def convertFeatureMask2FeatureIds(self, mask):
        """Returns feature ids corresponding to non-zero elements in the mask.

        :Parameters:
            mask: 1d ndarray
                Feature mask.

        :Returns:
            ndarray: integer
                Ids of non-zero (non-False) mask elements.
        """
        return mask.nonzero()[0]



    # read-only class properties
    nsamples        = property( fget=getNSamples )
    nfeatures       = property( fget=getNFeatures )

# Following attributes adherent to the basic dataset
Dataset._registerAttribute("labels",  "_data", hasunique=True)
Dataset._registerAttribute("chunks",  "_data", hasunique=True)
