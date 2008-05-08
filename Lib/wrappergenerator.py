#!/usr/bin/env python
# Python wrapper generation
# Created by David P. Grote, March 6, 1998
# Modified by T. B. Yang, May 21, 1998
# $Id: wrappergenerator.py,v 1.54 2008/05/08 21:20:54 dave Exp $

import sys
import os.path
from interfaceparser import processfile
import string
import re
import fvars
import getopt
import pickle
from cfinterface import *
import wrappergen_derivedtypes
import md5

class PyWrap:
  """
Usage:
  -a       All groups will be allocated on initialization
  -t ARCH  Build for specified architecture (default is HP700)
  -d <.scalars file>  a .scalars file in another module that this module depends on
  -F <compiler> The fortran compiler being used. This is needed since some
                operations depend on the compiler specific oddities.
  --f90    F90 syntax will be assumed
  --nowritemodules The modules will not be written out, assuming
                   that they are already written.
  --macros pkg.v Other interface files that are needed for the definition
                 of macros.
  --timeroutines Calls to the routines from python will be timed
  file1    Main variable description file for the package
  [file2, ...] Subsidiary variable description files
  """

  def __init__(self,ifile,pname,f90=1,initialgallot=1,writemodules=1,
               otherinterfacefiles=[],other_scalar_vars=[],timeroutines=0,
               otherfortranfiles=[],fcompname=None):
    self.ifile = ifile
    self.pname = pname
    self.f90 = f90
    self.initialgallot = initialgallot
    self.writemodules = writemodules
    self.timeroutines = timeroutines
    self.otherinterfacefiles = otherinterfacefiles
    self.other_scalar_vars = other_scalar_vars
    self.otherfortranfiles = otherfortranfiles
    self.fcompname = fcompname
    self.isz = isz # isz defined in cfinterface

    self.processvariabledescriptionfile()

  def cname(self,n):
    # --- Standard name of the C interface to a Fortran routine
    # --- pkg_varname
    return self.pname+'_'+n

  transtable = (10*string.ascii_lowercase)[:256]
  def fsub(self,prefix,suffix=''):
    """
    The fortran standard limits routine names to 31 characters. If the
    routine name is longer than that, this routine takes the first 15
    characters and and creates a hashed string based on the full name to get
    the next 16. This does not guarantee uniqueness, but the nonuniqueness
    should be minute.
    """
    name = self.pname+prefix+suffix
    if len(name) < 32: return name
    hash = string.translate(md5.new(name).digest(),PyWrap.transtable)
    return name[:15] + hash

  def prefixdimsc(self,dim,sdict):
    # --- Convert fortran variable name into reference from list of variables.
    sl=re.split('[ ()/\*\+\-]',dim)
    for ss in sl:
      if re.search('[a-zA-Z]',ss) != None:
        if sdict.has_key (ss):
          dim = re.sub(ss,
                   '*(long *)'+self.pname+'_fscalars['+repr(sdict[ss])+'].data',
                   dim,count=1)
        else:
          for other_vars in self.other_scalar_vars:
            other_dict = other_vars[0]
            if other_dict.has_key (ss):
              dim = re.sub(ss,'*(long *)'+other_dict['_module_name_']+
                        '_fscalars['+repr(other_dict[ss])+'].data',dim,count=1)
              break
          else:
            raise ss + ' is not declared in the interface file'
    return string.lower(dim)

  # --- Convert dimensions for unspecified arrays
  def prefixdimsf(self,dim):
    # --- Check for any unspecified dimensions and replace it with an element
    # --- from the dims array.
    sl = re.split(',',dim[1:-1])
    for i in range(len(sl)):
      if sl[i] == ':': sl[i] = 'dims__(%d)'%(i+1)
    dim = '(' + string.join(sl,',') + ')'
    return string.lower(dim)

  def dimsgroups(self,dim,sdict,slist):
    # --- Returns a list of group names that contain the variables listed in
    # --- a dimension statement
    groups = []
    sl=re.split('[ (),:/\*\+\-]',dim)
    for ss in sl:
      if re.search('[a-zA-Z]',ss) != None:
        if sdict.has_key(ss):
          groups.append(slist[sdict[ss]].group)
        else:
          for other_vars in self.other_scalar_vars:
            other_dict = other_vars[0]
            other_list = other_vars[1]
            if other_dict.has_key(ss):
              groups.append(other_list[other_dict[ss]].group)
              break
          else:
            raise ss + ' is not declared in the interface file'
    return groups

  def cw(self,text,noreturn=0):
    if noreturn:
      self.cfile.write(text)
    else:
      self.cfile.write(text+'\n')
  def fw(self,text,noreturn=0):
    if len(text) > 132:
      # --- If the line is too long, then break it up, adding line
      # --- continuation marks in between any variable names.
      for i in range(132,len(text),132):
        # --- \W matches anything but a letter or number.
        ss = re.search('\W',text[i::-1])
        assert ss is not None,\
               "Forthon can't find a place to break up this line:\n"+text
        text = text[:i-ss.start()] + '&\n' + text[i-ss.start():]
    if noreturn:
      self.ffile.write(text)
    else:
      self.ffile.write(text+'\n')

  def setffile(self):
    """Set the ffile attribute, which is the fortran file object.
It the attribute hasn't been created, then open the file with write status.
If it has, and the file is closed, then open it with append status.
    """
    if 'ffile' in self.__dict__: status = 'a'
    else:                        status = 'w'
    if (status == 'w' or
        (status == 'a' and self.ffile.closed)):
      if self.f90:
        self.ffile = open(self.pname+'_p.F90',status)
      else:
        self.ffile = open(self.pname+'_p.m',status)

  def processvariabledescriptionfile(self):
    """Read in and parse the variable description file and create the lists
of scalars and arrays.
    """

    # --- Get the list of variables and subroutine from the var file
    vlist,hidden_vlist,typelist = processfile(self.pname,self.ifile,
                                              self.otherinterfacefiles,
                                              self.timeroutines)

    # --- Get a list of all of the group names which have variables in it
    # --- (only used when writing fortran files but done here while complete
    # --- list of variables is still in one place, vlist).
    currentgroup = ''
    groups = []
    for v in vlist:
      if not v.function and v.group != currentgroup:
        groups.append(v.group)
        currentgroup = v.group

    # --- Get a list of all of the hidden group names.
    current_hidden_group = ''
    hidden_groups = []
    for hv in hidden_vlist:
      if not hv.function and hv.group != current_hidden_group:
        hidden_groups.append(hv.group)
        current_hidden_group = hv.group
  
    # --- Select out all of the scalars and build a dictionary
    # --- The dictionary is used to get number of the variables use as
    # --- dimensions for arrays.
    slist = []
    sdict = {}
    i = 0
    temp = vlist[:]
    for v in temp:
      if not v.dims and not v.function:
        slist.append(v)
        sdict[v.name] = i
        i = i + 1
        vlist.remove(v)

    # --- Select out all of the arrays
    alist = []
    i = 0
    temp = vlist[:]
    for v in temp:
      if not v.function:
        alist.append(v)
        i = i + 1
        vlist.remove(v)
    temp = []

    # --- The remaining elements should all be functions
    flist = vlist

    self.typelist = typelist
    self.slist = slist
    self.sdict = sdict
    self.alist = alist
    self.flist = flist
    self.groups = groups
    self.hidden_groups = hidden_groups

  ###########################################################################
  def createmodulefile(self):
    # --- This is the routine that does all of the work

    # --- Create the module file
    self.cfile = open(self.pname+'pymodule.c','w')
    self.cw('#include "Forthon.h"')
    self.cw('#include <setjmp.h>')
    self.cw('ForthonObject *'+self.pname+'Object;')

    # --- Print out the external commands
    self.cw('extern jmp_buf stackenvironment;')
    self.cw('extern void '+fname(self.fsub('passpointers'))+'(void);')
    self.cw('extern void '+fname(self.fsub('nullifypointers'))+'(void);')
    if not self.f90:
      self.cw('extern void '+self.pname+'data();')

    # --- fortran routine prototypes
    for f in self.flist:
      # --- Functions
      self.cw('extern '+fvars.ftoc(f.type)+' '+fnameofobj(f)+'(',noreturn=1)
      i = 0
      istr = 0
      if len(f.args) == 0: self.cw('void',noreturn=1)
      for a in f.args:
        if i > 0:
          self.cw(',',noreturn=1)
        i = i + 1
        self.cw(fvars.ftoc(a.type)+' ',noreturn=1)
        if a.type == 'string' or a.type == 'character':
          istr = istr + 1
        else:
          self.cw('*',noreturn=1)
        self.cw(a.name,noreturn=1)
      if charlen_at_end:
        for i in range(istr):
          self.cw(',int sl'+repr(i),noreturn=1)
      self.cw(');')
    for t in self.typelist:
      self.cw('extern PyObject *'+self.cname(t.name)+'New(PyObject *self, PyObject *args);')
    self.cw('')

    # --- setpointer and getpointer routine for f90
    # --- Note that setpointers get written out for all derived types -
    # --- for non-dynamic derived types, the setpointer routine does a copy.
    if self.f90:
      for s in self.slist:
        if s.dynamic or s.derivedtype:
          self.cw('extern void '+fname(self.fsub('setpointer',s.name))+
                  '(char *p,long *cobj__);')
        if s.dynamic:
          self.cw('extern void '+fname(self.fsub('getpointer',s.name))+
                  '(ForthonObject **cobj__,long *obj,long *createnew);')
      for a in self.alist:
        self.cw('extern void '+fname(self.fsub('setpointer',a.name))+
                '(char *p,long *cobj__,npy_intp *dims__);')
        if re.search('fassign',a.attr):
          self.cw('extern void '+fname(self.fsub('getpointer',a.name))+
                  '(long *i,long *cobj__);')

    ###########################################################################
    # --- Write declarations of c pointers to fortran variables

    # --- Declare scalars from other modules
    for other_vars in self.other_scalar_vars:
      other_dict = other_vars[0]
      self.cw('extern Fortranscalar '+other_dict['_module_name_']+
              '_fscalars[];')

    # --- Scalars
    self.cw('int '+self.pname+'nscalars = '+repr(len(self.slist))+';')
    if len(self.slist) > 0:
      self.cw('Fortranscalar '+self.pname+'_fscalars['+repr(len(self.slist))+']={')
      for i in range(len(self.slist)):
        s = self.slist[i]
        if (self.f90) and s.derivedtype:
          setpointer = '*'+fname(self.fsub('setpointer',s.name))
          if s.dynamic:
            getpointer = '*'+fname(self.fsub('getpointer',s.name))
          else:
            getpointer = 'NULL'
        else:
          setpointer = 'NULL'
          getpointer = 'NULL'
        self.cw('{PyArray_%s,'%fvars.ftop(s.type) + 
                 '"%s",'%s.type +
                 '"%s",'%s.name + 
                 'NULL,' + 
                 '"%s",'%s.group + 
                 '"%s",'%s.attr + 
                 '"%s",'%string.replace(repr(s.comment)[1:-1],'"','\\"') + 
                 '%i,'%s.dynamic + 
                 '%s,'%setpointer + 
                 '%s}'%getpointer,noreturn=1)
        if i < len(self.slist)-1: self.cw(',')
      self.cw('};')
    else:
      self.cw('Fortranscalar *'+self.pname+'_fscalars=NULL;')

    # --- Arrays
    self.cw('int '+self.pname+'narrays = '+repr(len(self.alist))+';')
    if len(self.alist) > 0:
      self.cw('static Fortranarray '+
              self.pname+'_farrays['+repr(len(self.alist))+']={')
      for i in range(len(self.alist)):
        a = self.alist[i]
        if (self.f90) and a.dynamic:
          setpointer = '*'+fname(self.fsub('setpointer',a.name))
        else:
          setpointer = 'NULL'
        if (self.f90) and re.search('fassign',a.attr):
          getpointer = '*'+fname(self.fsub('getpointer',a.name))
        else:
          getpointer = 'NULL'
        if a.data and a.dynamic:
          initvalue = a.data[1:-1]
        else:
          initvalue = '0'
        self.cw('{PyArray_%s,'%fvars.ftop(a.type) +
                  '%d,'%a.dynamic +
                  '%d,'%len(a.dims) +
                  'NULL,' +
                  '"%s",'%a.name +
                  '{NULL},' +
                  '%s,'%setpointer +
                  '%s,'%getpointer +
                  '%s,'%initvalue +
                  'NULL,' +
                  '"%s",'%a.group +
                  '"%s",'%a.attr +
                  '"%s",'%string.replace(repr(a.comment)[1:-1],'"','\\"') +
                  '"%s"}'%a.dimstring,noreturn=1)
        if i < len(self.alist)-1: self.cw(',')
      self.cw('};')
    else:
      self.cw('static Fortranarray *'+self.pname+'_farrays=NULL;')

# Some extra work is needed to get the getset attribute access scheme working.
#   # --- Write out the table of getset routines
#   self.cw('')
#   self.cw('static PyGetSetDef '+self.pname+'_getseters[] = {')
#   for i in range(len(self.slist)):
#     s = self.slist[i]
#     if s.type == 'real': gstype = 'double'
#     elif s.type == 'integer': gstype = 'integer'
#     elif s.type == 'complex': gstype = 'cdouble'
#     else:                    gstype = 'derivedtype'
#     self.cw('{"'+s.name+'",(getter)Forthon_getscalar'+gstype+
#                          ',(setter)Forthon_setscalar'+gstype+
#                    ',"%s"'%string.replace(repr(s.comment)[1:-1],'"','\\"') +
#                         ',(void *)'+repr(i)+'},')
#   for i in range(len(self.alist)):
#     a = self.alist[i]
#     self.cw('{"'+a.name+'",(getter)Forthon_getarray'+
#                          ',(setter)Forthon_setarray'+
#                    ',"%s"'%string.replace(repr(a.comment)[1:-1],'"','\\"') +
#                         ',(void *)'+repr(i)+'},')
#   self.cw('{"scalardict",(getter)Forthon_getscalardict,'+
#                         '(setter)Forthon_setscalardict,'+
#           '"internal scalar dictionary",NULL},')
#   self.cw('{"arraydict",(getter)Forthon_getarraydict,'+
#                        '(setter)Forthon_setarraydict,'+
#           '"internal array dictionary",NULL},')
#   self.cw('{NULL}};')

    ###########################################################################
    ###########################################################################
    # --- Now, the fun part, writing out the wrapper for the subroutine and
    # --- function calls.
    for f in self.flist:
      # --- Write out the documentation first.
      docstring = ('static char doc_'+self.cname(f.name)+'[] = "'+f.name+
                   f.dimstring+repr(f.comment)[1:-1]+'";')
      # --- Replaces newlines with '\\n' so that the string is all on one line
      # --- in the C coding.
      docstring = re.sub(r'\
','\\\\n',docstring)
      self.cw(docstring)
      # --- Now write out the wrapper
      self.cw('static PyObject *')
      self.cw(self.cname(f.name)+'(PyObject *self, PyObject *args)')
      self.cw('{')

      # --- With arguments, it gets very messy
      lv = repr(len(f.args))
      if len(f.args) > 0:
        self.cw('  PyObject * pyobj['+lv+'];')
        self.cw('  PyArrayObject * ax['+lv+'];')
        self.cw('  int i,argno=0;')

      self.cw('  char e[256];')

      if self.timeroutines:
        # --- Setup for the timer, getting time routine started.
        self.cw('  double time1,time2;')
        self.cw('  time1 = cputime();')

      # --- For character arguments, need to create an FSTRING array.
      istr = 0
      for a in f.args:
        if a.type == 'string' or a.type == 'character':
          istr = istr + 1
      if istr > 0:
        self.cw('  FSTRING fstr['+repr(istr)+'];')

      # --- If this is a function, set up variables to hold return value
      if f.type != 'void':
        self.cw('  PyObject * ret_val;')
        self.cw('  '+fvars.ftoc(f.type)+' r;')

      # --- Set all of the ax's to NULL
      if len(f.args) > 0:
        self.cw('  for (i=0;i<'+repr(len(f.args))+';i++) ax[i] = NULL;')

      # --- Parse incoming arguments into a list of PyObjects
      self.cw('  if (!PyArg_ParseTuple(args, "'+'O'*len(f.args)+'"',noreturn=1)
      for i in range(len(f.args)):
        self.cw(',&pyobj['+repr(i)+']',noreturn=1)
      self.cw(')) return NULL;')

      # --- Loop over arguments, extracting the data addresses.
      # --- Convert all arguments into arrays. This allows complete flexibility
      # --- in what can be passed to fortran functions.
      istr = 0
      for i in range(len(f.args)):
        self.cw('  argno++;')
        if not fvars.isderivedtype(f.args[i]):
          self.cw('  if (!Forthon_checksubroutineargtype(pyobj['+repr(i)+'],'+
              'PyArray_'+fvars.ftop(f.args[i].type,1)+','+repr(i)+')) {')
          self.cw('    sprintf(e,"Argument '+repr(i+1)+ ' in '+f.name+
                               ' has the wrong type");')
          self.cw('    goto err;}')
          if f.function == 'fsub':
            self.cw('  ax['+repr(i)+'] = FARRAY_FROMOBJECT('+
                  'pyobj['+repr(i)+'], PyArray_'+fvars.ftop(f.args[i].type)+');')
          elif f.function == 'csub':
            self.cw('  ax['+repr(i)+']=(PyArrayObject *)PyArray_ContiguousFromObject('+
                  'pyobj['+repr(i)+'], PyArray_'+fvars.ftop(f.args[i].type)+',0,0);')
          self.cw('  if (ax['+repr(i)+'] == NULL) {')
          self.cw('    sprintf(e,"There is an error in argument '+repr(i+1)+
                               ' in '+f.name+'");')
          self.cw('    goto err;}')
          if f.args[i].type == 'string' or f.args[i].type == 'character':
            self.cw('  FSETSTRING(fstr[%d],PyArray_BYTES(ax[%d]),PyArray_SIZE(ax[%d]));'
                    %(istr,i,i))
            istr = istr + 1
        else:
          self.cw('  {')
          self.cw('  PyObject *t;')
          self.cw('  t = PyObject_Type(pyobj['+repr(i)+']);')
          self.cw('  if (strcmp(((PyTypeObject *)t)->tp_name,"Forthon") != 0) {')
          self.cw('     sprintf(e,"Argument '+repr(i+1)+ ' in '+f.name+
                               ' has the wrong type");')
          self.cw('     goto err;}')
          self.cw('  Py_DECREF(t);')
          typename = '((ForthonObject *)pyobj['+repr(i)+'])->typename'
          self.cw('  if (strcmp('+typename+',"'+f.args[i].type+'") != 0) {')
          self.cw('     sprintf(e,"Argument '+repr(i+1)+ ' in '+f.name+
                               ' has the wrong type");')
          self.cw('     goto err;}')
          self.cw('  }')

      # --- Write the code checking dimensions of arrays
      # --- This must be done after all of the ax's are setup in case the
      # --- dimensioning arguments come after the array argument.
      # --- This creates a local variable with the same name as the argument
      # --- and gives it the value passed in. Then any expressions in the
      # --- dimensions statements will be explicitly evaluated in C.
      if len(f.dimvars) > 0:
        self.cw('  {')
        self.cw('  int _n;')
        # --- Declare the dimension variables.
        for var,i in f.dimvars:
          self.cw('  '+fvars.ftoc(var.type)+' '+var.name+'=*'+
                  '('+fvars.ftoc(var.type)+' *)(PyArray_BYTES(ax['+repr(i)+']));')
        # --- Loop over the arguments, looking for dimensioned arrays
        i = -1
        for arg in f.args:
          i += 1
          if len(arg.dims) > 0:
            # --- Set argno in case there is an error
            self.cw('  argno = %d;'%(i+1))
            # --- Check the rank of the input argument
            # --- For a 1-D argument, allow a scaler to be passed, which has
            # --- a number of dimensions (nd) == 0.
            self.cw('  if (!(PyArray_NDIM(ax[%d]) == %d'%(i,len(arg.dims)),noreturn=1)
            if len(arg.dims) == 1:
              self.cw('      ||PyArray_NDIM(ax[%d]) == 0)) {'%i)
            else:
              self.cw('      )) {')
            self.cw('    sprintf(e,"Argument %d in %s '%(i+1,f.name) +
                             'has the wrong number of dimensions");')
            self.cw('    goto err;}')
            j = -1

            # --- Skip the check of dimension sizes if the total size of
            # --- the array should be zero. This gets around an issue with
            # --- numpy that zero length arrays seem to be always in
            # --- C ordering.
            self.cw('  if (1',noreturn=1)
            for dim in arg.dims:
              self.cw('*(('+dim.high+')-('+dim.low+')+1)',noreturn=1)
            self.cw(' != 0) {')

            for dim in arg.dims:
              j += 1
              # --- Compare each dimension with its specified value
              # --- For a 1-D argument, allow a scalar to be passed, which has
              # --- a number of dimensions (nd) == 0, but only if the
              # --- argument needs to have a length of 0 or 1.
              self.cw('    _n = ('+dim.high+')-('+dim.low+')+1;')
              if len(arg.dims) == 1:
                self.cw('    if (!((_n==0||_n==1)||(PyArray_NDIM(ax[%d]) > 0 &&'%i,
                        noreturn=1)
              else:
                self.cw('    if (!((',noreturn=1)
              self.cw('_n == (int)(PyArray_DIMS(ax[%d])[%d])))) {'%(i,j))
              self.cw('      sprintf(e,"Dimension '+repr(j+1)+' of argument '+
                               repr(i+1)+ ' in '+f.name+
                               ' has the wrong size");')
              self.cw('      goto err;}')
            self.cw('  }')
        self.cw('  }')

      # --- Make a call to setjmp to save the state in case an error happens.
      # --- If there was an error, setjmp returns 1, so exit out.
      self.cw('  if (setjmp(stackenvironment)) goto err;')

      # --- Write the actual call to the fortran routine.
      if f.type == 'void':
        self.cw('  ')
      else:
        self.cw('  r = ')
      self.cw(fnameofobj(f)+'(',noreturn=1)
      i = 0
      istr = 0
      for a in f.args:
        if i > 0:
          self.cw(',',noreturn=1)
        if fvars.isderivedtype(a):
          self.cw('((ForthonObject *)(pyobj['+repr(i)+']))->fobj',noreturn=1)
        elif a.type == 'string' or a.type == 'character':
          self.cw('fstr[%d]'%(istr),noreturn=1)
          istr = istr + 1
        else:
          self.cw('('+fvars.ftoc(a.type)+' *)(PyArray_BYTES(ax['+repr(i)+']))',noreturn=1)
        i = i + 1
      if charlen_at_end:
        i = 0
        istr = 0
        for a in f.args:
          if a.type == 'string' or a.type == 'character':
            self.cw(',PyArray_SIZE(ax['+repr(i)+'])',noreturn=1)
            istr = istr + 1
          i = i + 1

      self.cw(');') # --- Closing parenthesis on the call list

      # --- Copy the data that was sent to the routine back into the passed
      # --- in object if it is an PyArray.
      # --- Decrement reference counts of array objects created.
      # --- This is now handled by a separate subroutine included in Forthon.h
      if len(f.args) > 0:
        self.cw('  Forthon_restoresubroutineargs('+repr(len(f.args))+
                   ',pyobj,ax);')

      if self.timeroutines:
        # --- Now get ending time and add to timer variable
        self.cw('  time2 = cputime();')
        self.cw('  *(double *)'+self.pname+'_fscalars['+
                     repr(self.sdict[f.name+'runtime'])+'].data += (time2-time1);')

      # --- Write return sequence
      if f.type == 'void':
        self.cw('  returnnone;')
      else:
        self.cw('  ret_val = Py_BuildValue ("'+fvars.fto1[f.type]+'", r);')
        self.cw('  return ret_val;')

      # --- Error section, in case there was an error above or in the
      # --- fortran call
      self.cw('err:') 

      # --- Before setting the error string, check if an error was raised
      # --- somewhere else.
      self.cw('  if (!PyErr_Occurred())')
      self.cw('    PyErr_SetString(ErrorObject,e);')

      if len(f.args) > 0:
        # --- Decrement reference counts of array objects created.
        self.cw('  for (i=0;i<'+repr(len(f.args))+';i++)')
        self.cw('    if (ax[i] != NULL) {Py_XDECREF(ax[i]);}')

      self.cw('  return NULL;')

      self.cw('}')

    # --- Add blank line
    self.cw('')

    ###########################################################################
    # --- Write out method list
    self.cw('static struct PyMethodDef '+self.pname+'_methods[] = {')
    for f in self.flist:
      if f.function:
        self.cw('{"'+f.name+'",(PyCFunction)'+self.cname(f.name)+',1,'+
                'doc_'+self.cname(f.name)+'},')
    for t in self.typelist:
      self.cw('{"'+t.name+'",(PyCFunction)'+self.cname(t.name)+'New,1,'+
              '"Creates a new instance of fortran derived type '+t.name+'"},')
    self.cw('{NULL,NULL}};')
    self.cw('')

    ###########################################################################
    # --- Write static array initialization routines
    self.cw('void '+self.pname+'setstaticdims(ForthonObject *self)')
    self.cw('{')
  
    i = -1
    for a in self.alist:
      i = i + 1
      vname = self.pname+'_farrays['+repr(i)+']'
      if a.dims and not a.dynamic:
        j = 0
        for d in a.dims:
          self.cw('  '+vname+'.dimensions['+repr(len(a.dims)-1-j)+'] = (npy_intp)(('+
                  d.high+') - ('+d.low+') + 1);')
          j = j + 1

    self.cw('}')
    self.cw('')

    ###########################################################################
    # --- Write routine which sets the dimensions of the dynamic arrays.
    # --- This is done in a seperate routine so it only appears once.
    # --- A routine is written out for each group which has dynamic arrays. Then
    # --- a routine is written which calls all of the individual group routines.
    # --- That is done to reduce the strain on the compiler by reducing the size
    # --- of the routines. (In fact, in one case, with everything in one
    # --- routine the cc compiler was giving a core dump!)
    # --- Loop over the variables. This assumes that the variables are sorted
    # --- by group.
    i = -1
    currentgroup = ''
    dyngroups = []
    for a in self.alist:
      if a.group != currentgroup and a.dynamic:
        if currentgroup != '':
          self.cw('  }}')
        currentgroup = a.group
        if len(dyngroups) > 0: dyngroups[-1][2] = i
        dyngroups.append([currentgroup,i+1,len(self.alist)])
        self.cw('static void '+self.pname+'setdims'+currentgroup+'(char *name,long i)')
        self.cw('{')
        self.cw('  if (strcmp(name,"'+a.group+'") || strcmp(name,"*")) {')

      i = i + 1
      vname = self.pname+'_farrays['+repr(i)+']'
      if a.dynamic == 1 or a.dynamic == 2:
        j = 0
        self.cw('  if (i == -1 || i == %d) {'%i)
        # --- create lines of the form dims[1] = high-low+1, in reverse order
        for d in a.dims:
          if d.high == '': continue
          self.cw('   '+vname+'.dimensions['+repr(len(a.dims)-1-j)+']=(npy_intp)((int)',
                  noreturn=1)
          j = j + 1
          if re.search('[a-zA-Z]',d.high) == None:
            self.cw('('+d.high+')-',noreturn=1)
          else:
            self.cw('('+self.prefixdimsc(d.high,self.sdict)+')-',noreturn=1)
          if re.search('[a-zA-Z]',d.low) == None:
            self.cw('('+d.low+')+1);')
          else:
            self.cw('('+self.prefixdimsc(d.low,self.sdict)+')+1);',noreturn=1)
        self.cw('  }')

    if currentgroup != '':
      self.cw('  }}')

    # --- Now write out the setdims routine which calls of the routines
    # --- for the individual groups.
    self.cw('void '+self.pname+'setdims(char *name,ForthonObject *obj,long i)')
    self.cw('{')
    for groupinfo in dyngroups:
        self.cw('  if (i == -1 || (%d <= i && i <= %d))'%tuple(groupinfo[1:]),
                noreturn=1)
        self.cw('  '+self.pname+'setdims'+groupinfo[0]+'(name,i);')
    self.cw('}')
  
    self.cw('')

    ###########################################################################
    # --- Write set pointers routine which gets all of the fortran pointers
    self.cw('void '+fname(self.fsub('setscalarpointers'))+
            '(long *i,char *p',noreturn=1)
    if machine=='J90':
      self.cw(',int *iflag)')
    else:
      self.cw(')')
    self.cw('{')
    self.cw('  /* Get pointers for the scalars */')
    self.cw('  '+self.pname+'_fscalars[*i].data = (char *)p;')
    if machine=='J90':
      self.cw('    if (iflag) {')
      self.cw('      '+self.pname+'_fscalars[*i].data=_fcdtocp((_fcd)p);}')
    self.cw('}')

    # --- A serarate routine is needed for derived types since the cobj__
    # --- that is passed in is already a pointer, so **p is needed.
    self.cw('void '+fname(self.fsub('setderivedtypepointers'))+
            '(long *i,char **p)')
    self.cw('{')
    self.cw('  /* Get pointers for the scalars */')
    self.cw('  '+self.pname+'_fscalars[*i].data = (char *)(*p);')
    self.cw('}')

    # --- Get pointer to an array. This takes an integer to specify which array
    self.cw('void '+fname(self.fsub('setarraypointers'))+
            '(long *i,char *p',noreturn=1)
    if machine=='J90':
      self.cw(',int *iflag)')
    else:
      self.cw(')')
    self.cw('{')
    self.cw('  /* Get pointers for the arrays */')
    self.cw('  '+self.pname+'_farrays[*i].data.s = (char *)p;')
    if machine=='J90':
      self.cw('    if (iflag) {')
      self.cw('      '+self.pname+'_farrays[*i].data.s=_fcdtocp((_fcd)p);}')
    self.cw('}')

    # --- This takes a Fortranarray object directly.
    self.cw('void '+fname(self.fsub('setarraypointersobj'))+
            '(Fortranarray *farray,char *p',noreturn=1)
    if machine=='J90':
      self.cw(',int *iflag)')
    else:
      self.cw(')')
    self.cw('{')
    self.cw('  /* Get pointers for the arrays */')
    self.cw('  farray->data.s = (char *)p;')
    if machine=='J90':
      self.cw('    if (iflag) {')
      self.cw('      farray->data.s=_fcdtocp((_fcd)p);}')
    self.cw('}')

    # --- This routine gets the dimensions from an array. It is called from
    # --- fortran and the last argument should be shape(array).
    # --- This is only used for routines with the fassign attribute.
    # --- Note that the dimensions are stored in C order.
    self.cw('void '+fname(self.fsub('setarraydims'))+
            '(Fortranarray *farray,long *dims)')
    self.cw('{')
    if self.f90:
      self.cw('  int id;')
      self.cw('  for (id=0;id<farray->nd;id++)')
      self.cw('    farray->dimensions[farray->nd-1-id] = (npy_intp)(dims[id]);')
    self.cw('}')

    ###########################################################################
    # --- And finally, the initialization function
    self.cw('#ifndef PyMODINIT_FUNC')
    self.cw('#define PyMODINIT_FUNC void')
    self.cw('#endif')
    self.cw('PyMODINIT_FUNC')
    self.cw('init'+self.pname+'py(void)')
    self.cw('{')
    self.cw('  PyObject *m;')
    if self.fcompname == 'nag':
      self.cw('  int argc; char **argv;')
      self.cw('  Py_GetArgcArgv(&argc,&argv);')
      self.cw('  f90_init(argc,argv);')
#   self.cw('  ForthonType.tp_getset = '+self.pname+'_getseters;')
#   self.cw('  ForthonType.tp_methods = '+self.pname+'_methods;')
    self.cw('  if (PyType_Ready(&ForthonType) < 0)')
    self.cw('    return;')
    self.cw('  m = Py_InitModule("'+self.pname+'py",'+self.pname+'_methods);')
   #self.cw('  PyModule_AddObject(m,"'+self.pname+'Type",'+
   #               '(PyObject *)&ForthonType);')
    self.cw('  '+self.pname+'Object=(ForthonObject *)'+
               'PyObject_GC_New(ForthonObject, &ForthonType);')
              #'ForthonObject_New(NULL,NULL);')
    self.cw('  '+self.pname+'Object->name = "'+self.pname+'";')
    self.cw('  '+self.pname+'Object->typename = "'+self.pname+'";')
    self.cw('  '+self.pname+'Object->nscalars = '+self.pname+'nscalars;')
    self.cw('  '+self.pname+'Object->fscalars = '+self.pname+'_fscalars;')
    self.cw('  '+self.pname+'Object->narrays = '+self.pname+'narrays;')
    self.cw('  '+self.pname+'Object->farrays = '+self.pname+'_farrays;')
    self.cw('  '+self.pname+'Object->setdims = *'+self.pname+'setdims;')
    self.cw('  '+self.pname+'Object->setstaticdims = *'+
                self.pname+'setstaticdims;')
    self.cw('  '+self.pname+'Object->fmethods = '+self.pname+'_methods;')
    self.cw('  '+self.pname+'Object->__module__ = Py_BuildValue("s","'+
                 self.pname+'py");')
    self.cw('  '+self.pname+'Object->fobj = NULL;')
    self.cw('  '+self.pname+'Object->fobjdeallocate = NULL;')
    self.cw('  '+self.pname+'Object->nullifycobj = NULL;')
    self.cw('  '+self.pname+'Object->allocated = 0;')
    self.cw('  '+self.pname+'Object->garbagecollected = 0;')
    self.cw('  PyModule_AddObject(m,"'+self.pname+'",(PyObject *)'+
                self.pname+'Object);')
    self.cw('  ErrorObject = PyString_FromString("'+self.pname+'py.error");')
    self.cw('  PyModule_AddObject(m,"'+self.pname+'error", ErrorObject);')
    self.cw('  PyModule_AddObject(m,"fcompname",'+
               'PyString_FromString("'+self.fcompname+'"));')
    self.cw('  if (PyErr_Occurred()) {')
    self.cw('    PyErr_Print();')
    self.cw('    Py_FatalError("can not initialize module '+self.pname+'");')
    self.cw('    }')
    self.cw('  import_array();')
    self.cw('  Forthon_BuildDicts('+self.pname+'Object);')
    self.cw('  ForthonPackage_allotdims('+self.pname+'Object);')
    self.cw('  '+fname(self.fsub('passpointers'))+'();')
    self.cw('  '+fname(self.fsub('nullifypointers'))+'();')
    self.cw('  ForthonPackage_staticarrays('+self.pname+'Object);')
    if not self.f90:
      self.cw('  '+fname(self.fsub('data'))+'();')
    if self.initialgallot:
      self.cw('  {')
      self.cw('  PyObject *s;')
      self.cw('  s = Py_BuildValue("(s)","*");')
      self.cw('  ForthonPackage_gallot((PyObject *)'+self.pname+'Object,s);')
      self.cw('  Py_XDECREF(s);')
      self.cw('  }')

    self.cw('  {')
    self.cw('  PyObject *m, *d, *f, *r;')
    self.cw('  r = NULL;')
    self.cw('  m = PyImport_ImportModule("Forthon");')
    self.cw('  if (m != NULL) {')
    self.cw('    d = PyModule_GetDict(m);')
    self.cw('    if (d != NULL) {')
    self.cw('      f = PyDict_GetItemString(d,"registerpackage");')
    self.cw('      if (f != NULL) {')
    self.cw('        r = PyObject_CallFunction(f,"Os",(PyObject *)'+
                self.pname+'Object,"'+self.pname+'");')
    self.cw('  }}}')
    self.cw('  if (NULL == r) {')
    self.cw('    if (PyErr_Occurred()) PyErr_Print();')
    self.cw('    Py_FatalError("unable to find a compatible Forthon module in which to register module ' + self.pname + '");')
    self.cw('  }')
    self.cw('  Py_XDECREF(m);')
    self.cw('  Py_XDECREF(r);')
    self.cw('  }')

    if machine=='win32':
      self.cw('  /* Initialize FORTRAN on CYGWIN */')
      self.cw(' initPGfortran();')

    self.cw('}')
    self.cw('')

    ###########################################################################
    # --- --- Close the c package module file
    self.cfile.close()

    ###########################################################################
    ###########################################################################
    ###########################################################################
    # --- Write out fortran initialization routines
    self.setffile()
    self.ffile.close()

    ###########################################################################
    ###########################################################################
    # --- Process any derived types
    wrappergen_derivedtypes.ForthonDerivedType(self.typelist,self.pname,
                               self.pname+'pymodule.c',
                               self.pname+'_p.F90',self.f90,self.isz,
                               self.writemodules,self.fcompname)
    ###########################################################################
    ###########################################################################

    self.setffile()

    ###########################################################################
    # --- Write out f90 modules, including any data statements
    if self.f90 and self.writemodules:
      self.writef90modules()

    ###########################################################################
    self.fw('SUBROUTINE '+self.fsub('passpointers')+'()')

    # --- Write out the Use statements
    for g in self.groups+self.hidden_groups:
      if self.f90:
       self.fw('  USE '+g)
      else:
       self.fw('  Use('+g+')')
 
    # --- Write out calls to c routine passing down pointers to scalars
    for i in range(len(self.slist)):
      s = self.slist[i]
      if s.dynamic: continue
      if s.derivedtype:
        # --- This is only called for static instances, so deallocatable is
        # --- set to false (the last argument).
        self.fw('  call init'+s.type+'py(int('+repr(i)+','+self.isz+'),'+s.name+','+
                s.name+'%cobj__,int(1,'+self.isz+'),int(0,'+self.isz+'))')
        self.fw('  call '+self.fsub('setderivedtypepointers')+'(int('+repr(i)+','+self.isz+'),'+s.name+'%cobj__)')
      else:
        self.fw('  call '+self.fsub('setscalarpointers')+'(int('+repr(i)+','+self.isz+'),'+s.name,
                noreturn=1)
        if machine == 'J90':
          if s.type == 'string' or s.type == 'character':
            self.fw(',int(1,'+self.isz+'))')
          else:
            self.fw(',int(0,'+self.isz+'))')
        else:
          self.fw(')')

    # --- Write out calls to c routine passing down pointers to arrays
    # --- For f90, setpointers is not needed for dynamic arrays but is called
    # --- anyway to get the numbering of arrays correct.
    if machine == 'J90':
      if a.type == 'string' or a.type == 'character':
        str = ',int(1,'+self.isz+'))'
      else:
        str = ',int(0,'+self.isz+'))'
    else:
      str = ')'
    for i in range(len(self.alist)):
      a = self.alist[i]
      if a.dynamic:
        if not self.f90:
          self.fw('  call '+self.fsub('setarraypointers')+'(int('+repr(i)+','+self.isz+'),'+
                  'p'+a.name+str)
      else:
        self.fw('  call '+self.fsub('setarraypointers')+'(int('+repr(i)+','+self.isz+'),'+a.name+str)

    # --- Finish the routine
    self.fw('  return')
    self.fw('end')

    ###########################################################################
    # --- Nullifies the pointers of all dynamic variables. This is needed
    # --- since in some compilers, the associated routine returns
    # --- erroneous information if the status of a pointer is undefined.
    # --- Pointers must be explicitly nullified in order to get
    # --- associated to return a false value.
    self.fw('SUBROUTINE '+self.fsub('nullifypointers')+'()')

    # --- Write out the Use statements
    for g in self.groups+self.hidden_groups:
      self.fw('  USE '+g)
 
    for i in range(len(self.slist)):
      s = self.slist[i]
      if s.dynamic: self.fw('  NULLIFY('+s.name+')')
    for i in range(len(self.alist)):
      a = self.alist[i]
      if a.dynamic: self.fw('  NULLIFY('+a.name+')')

    self.fw('  return')
    self.fw('end')
    ###########################################################################
    # --- Write routine for each dynamic variable which gets the pointer from the
    # --- wrapper
    if self.f90:
      for s in self.slist:
        self.fw('SUBROUTINE '+self.fsub('setpointer',s.name)+'(p__,cobj__)')
        self.fw('  USE '+s.group)
        self.fw('  integer('+self.isz+'):: cobj__')
        self.fw('  '+fvars.ftof(s.type)+',target::p__')
        if s.dynamic:
          self.fw('  '+s.name+' => p__')
        else:
          self.fw('  '+s.name+' = p__')
        self.fw('  RETURN')
        self.fw('END')
        if s.dynamic:
          # --- In all cases, it is not desirable to create a new instance,
          # --- for example when the object is being deleted.
          self.fw('SUBROUTINE '+self.fsub('getpointer',s.name)+
                                 '(cobj__,obj__,createnew__)')
          self.fw('  USE '+s.group)
          self.fw('  integer('+self.isz+'):: cobj__,obj__,createnew__')
          self.fw('  if (ASSOCIATED('+s.name+')) then')
          self.fw('    if ('+s.name+'%cobj__ == 0 .and. createnew__ == 1) then')
          self.fw('      call init'+s.type+'py(int(-1,'+self.isz+'),'+s.name+','+
                                               s.name+'%cobj__,int(0,'+self.isz+'),int(0,'+self.isz+'))')
          self.fw('    endif')
          self.fw('    cobj__ = '+s.name+'%cobj__')
          self.fw('  else')
          self.fw('    cobj__ = 0')
          self.fw('  endif')
          self.fw('  RETURN')
          self.fw('END')

      for a in self.alist:
        if a.dynamic:
          self.fw('SUBROUTINE '+self.fsub('setpointer',a.name)+'(p__,cobj__,dims__)')
          groups = self.dimsgroups(a.dimstring,self.sdict,self.slist)
          groupsprinted = [a.group]
          for g in groups:
            if g not in groupsprinted:
              self.fw('  USE '+g)
              groupsprinted.append(g)
          self.fw('  USE '+a.group)
          self.fw('  integer('+self.isz+'):: cobj__')
          if with_numpy:
            self.fw('  integer('+self.isz+'):: dims__('+repr(len(a.dims))+')')
          else:
            self.fw('  integer(4):: dims__('+repr(len(a.dims))+')')
          self.fw('  '+fvars.ftof(a.type)+',target::p__'+
                    self.prefixdimsf(a.dimstring))
          self.fw('  '+a.name+' => p__')
          self.fw('  return')
          self.fw('end')
          if re.search('fassign',a.attr):
            self.fw('SUBROUTINE '+self.fsub('getpointer',a.name)+'(i__,obj__)')
            self.fw('  USE '+a.group)
            self.fw('  integer('+self.isz+'):: i__,obj__')
            self.fw('  integer('+self.isz+'):: ss(%d)'%(len(a.dims)))
            self.fw('  if (.not. associated('+a.name+')) return')
            self.fw('  call '+self.fsub('setarraypointersobj')+'(i__,'+a.name+')')
            self.fw('  ss = shape('+a.name+')')
            self.fw('  call '+self.fsub('setarraydims')+'(i__,ss)')
            self.fw('  return')
            self.fw('end')

    ###########################################################################
    if not self.f90:
      # --- Write out fortran data routine, only for f77 version
      self.fw('      SUBROUTINE '+self.fsub('data')+'()')

      # --- Write out the Use statements
      for g in self.groups:
        self.fw('Use('+g+')')
     
      for hg in self.hidden_groups:
        self.fw('Use('+hg+')')

      self.fw('      integer iyiyiy')

      # --- Write out data statements
      for s in self.slist:
        if s.data:
          self.fw('      data '+s.name+s.data)
      for a in self.alist:
        if a.data and not a.dynamic:
          self.fw('      data '+a.name+a.data)

      self.fw('      iyiyiy=0')
      self.fw('      return')
      self.fw('      end')

    # --- --- Close fortran file
    self.ffile.close()
    scalar_pickle_file = open(self.pname + '.scalars','w')
    self.sdict ['_module_name_'] = self.pname
    pickle.dump (self.sdict, scalar_pickle_file)
    pickle.dump (self.slist, scalar_pickle_file)
    scalar_pickle_file.close()

  def writef90modules(self):
    """Write the fortran90 modules"""
    self.setffile()
    if   self.f90 : dyntype = 'pointer'
    if   self.fcompname == 'xlf': save = ',SAVE'
    else:                         save = ''
    for g in self.groups+self.hidden_groups:
      self.fw('MODULE '+g)
      # --- Check if any variables are derived types. If so, the module
      # --- containing the type must be used.
      printedtypes = []
      for v in self.slist + self.alist:
        if v.group == g and v.derivedtype:
          if v.type not in printedtypes:
            self.fw('  USE '+v.type+'module')
            printedtypes.append(v.type)
      self.fw('  SAVE')
      # --- Declerations for scalars and arrays
      for s in self.slist:
        if s.group == g:
          self.fw('  '+fvars.ftof(s.type),noreturn=1)
          if s.dynamic: self.fw(',POINTER',noreturn=1)
          self.fw(save+'::'+s.name,noreturn=1)
          if s.data: self.fw('='+s.data[1:-1],noreturn=1)
          self.fw('')
      for a in self.alist:
        if a.group == g:
          if a.dynamic:
            if a.type == 'character':
              self.fw('  character(len='+a.dims[0].high+'),'+dyntype+save+'::'+
                      a.name,noreturn=1)
              ndims = len(a.dims) - 1
            else:
              self.fw('  '+fvars.ftof(a.type)+','+dyntype+save+'::'+a.name,
                      noreturn=1)
              ndims = len(a.dims)
            if ndims > 0:
              self.fw('('+(ndims*':,')[:-1]+')',noreturn=1)
            self.fw('')
          else:
            if a.type == 'character':
              self.fw('  character(len='+a.dims[0].high+')'+save+'::'+a.name+
                      a.dimstring)
            else:
              self.fw('  '+fvars.ftof(a.type)+save+'::'+a.name+a.dimstring)
            if a.data:
              # --- Add line continuation marks if the data line extends over
              # --- multiple lines.
              dd = re.sub(r'\n','&\n',a.data)
              self.fw('  data '+a.name+dd)
      self.fw('END MODULE '+g)

###############################################################################
###############################################################################
###############################################################################
###############################################################################

module_prefix_pat = re.compile ('([a-zA-Z_][a-zA-Z0-9_]*)\.scalars')
def get_another_scalar_dict(file_name,other_scalar_vars):
  m = module_prefix_pat.search(file_name)
  if m.start() == -1: raise 'expect a .scalars file'
  f = open(file_name,'r')
  vars = []
  vars.append(pickle.load(f))
  vars.append(pickle.load(f))
  other_scalar_vars.append(vars)
  f.close()

def wrappergenerator_main(argv=None,writef90modulesonly=0):
  if argv is None: argv = sys.argv[1:]
  optlist,args=getopt.getopt(argv,'at:d:F:',
                     ['f90','f77','2underscores','no2underscores',
                      'nowritemodules',
                      'timeroutines','with-numpy','macros='])

  # --- Get package name from argument list
  try:
    pname = args[0]
    ifile = args[1]
    otherfortranfiles = args[2:]
    #pname = os.path.splitext(os.path.split(ifile)[1])[0]
    #pname = args[0][:re.search('\.',args[0]).start()]
  except IndexError:
    print PyWrap.__doc__
    sys.exit(1)

  # --- get other command line options and default actions
  initialgallot = 0
  fcompname = None
  f90 = 1
  writemodules = 1
  timeroutines = 0
  otherinterfacefiles = []

  # --- a list of scalar dictionaries from other modules.
  other_scalar_vars = []

  for o in optlist:
    if o[0]=='-a': initialgallot = 1
    elif o[0]=='-t': machine = o[1]
    elif o[0]=='-F': fcompname = o[1]
    elif o[0]=='--f90': f90 = 1
    elif o[0]=='--f77': f90 = 0
    elif o[0]=='-d': get_another_scalar_dict (o[1],other_scalar_vars)
    elif o[0]=='--nowritemodules': writemodules = 0
    elif o[0]=='--timeroutines': timeroutines = 1
    elif o[0]=='--macros': otherinterfacefiles.append(o[1])

  cc = PyWrap(ifile,pname,f90,initialgallot,writemodules,
              otherinterfacefiles,other_scalar_vars,timeroutines,
              otherfortranfiles,fcompname)
  if writef90modulesonly:
    cc.writef90modules()
  else:
    cc.createmodulefile()


# --- This might make some of the write statements cleaner.
# --- From http://aspn.activestate.com/ASPN/Python/Cookbook/
class PrintEval:
    def __init__(self, globals=None, locals=None):
        self.globals = globals or {}
        self.locals = locals or None
        
    def __getitem__(self, key):
        if self.locals is None:
            self.locals = sys._getframe(1).f_locals
        key = key % self
        return eval(key, self.globals, self.locals)

if __name__ == '__main__':
  wrappergenerator_main(sys.argv[1:])

