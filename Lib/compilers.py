"""Class which determines which fortran compiler to use and sets defaults
for it.
"""

import sys,os,re
import string
import struct

class FCompiler:
  """
Determines which compiler to use and sets up description of how to use it.
To add a new compiler, create a new method which a name using the format
machine_compiler. The first lines of the function must be of the following form
    if (self.findfile(compexec) and
        (self.fcompname==compname or self.fcompname is None)):
      self.fcompname = compname
where compexec is the executable name of the compiler and compname is a
descriptive (or company) name for the compiler. They can be the same.
In the function, the two attributes f90free and f90fixed must be defined. Note
that the final linking is done with gcc, so any fortran libraries will need to
be added to libs (and their locations to libdirs).
Also, the new function must be included in the while loop below in the
appropriate block for the machine.
  """

  def __init__(self,machine=None,debug=0,fcompname=None,static=0,implicitnone=1):
    if machine is None: machine = sys.platform
    self.machine = machine
    if self.machine <> 'win32':
      self.processor = os.uname()[4]
    else:
      self.processor = 'i686'
    self.paths = string.split(os.environ['PATH'],os.pathsep)

    self.fcompname = fcompname
    self.static = static
    self.implicitnone = implicitnone
    self.defines = []
    self.fopt = ''
    self.popt = ''
    self.libs = []
    self.libdirs = []
    self.forthonargs = []
    self.extra_link_args = []
    self.extra_compile_args = []
    self.define_macros = []

    # --- Pick the fortran compiler
    # --- When adding a new compiler, it must be listed here under the correct
    # --- machine name.
    while 1:
      if self.machine == 'linux2':
        if self.linux_intel8() is not None: break
        if self.linux_intel() is not None: break
        if self.linux_g95() is not None: break
        if self.linux_pg() is not None: break
        if self.linux_absoft() is not None: break
        if self.linux_lahey() is not None: break
        if self.linux_pathscale() is not None: break
      elif self.machine == 'darwin':
        if self.macosx_xlf() is not None: break
        if self.macosx_g95() is not None: break
        if self.macosx_gfortran() is not None: break
        if self.macosx_absoft() is not None: break
        if self.macosx_nag() is not None: break
        if self.macosx_gnu() is not None: break
      elif self.machine == 'cygwin':
        if self.cygwin_g95() is not None: break
      elif self.machine == 'win32':
        if self.win32_pg() is not None: break
        if self.win32_intel() is not None: break
      elif self.machine == 'aix4' or self.machine == 'aix5':
        if self.aix_xlf() is not None: break
        if self.aix_mpxlf() is not None: break
        if self.aix_xlf_r() is not None: break
        if self.aix_mpxlf64() is not None: break
        if self.aix_pghpf() is not None: break
      else:
        raise SystemExit,'Machine type %s is unknown'%self.machine
      raise SystemExit,'Fortran compiler not found'

    # --- The following two quantities must be defined.
    try:
      self.f90free
      self.f90fixed
    except:
      # --- Note that this error should never happed (except during debugging)
      raise "The fortran compiler definition is not correct, f90free and f90fixed must be defined."

    if debug:
      self.fopt = '-g'
      self.popt = '-g'
      self.extra_link_args += ['-g']
      self.extra_compile_args += ['-g']

    # --- Add the compiler name to the forthon arguments
    self.forthonargs += ['-F '+self.fcompname]

  def findfile(self,file,followlinks=1):
    if self.machine == 'win32': file = file + '.exe'
    for path in self.paths:
      try:
        if file in os.listdir(path):
          # --- Check if the path is a link
          if followlinks:
            try:
              path = os.path.dirname(os.readlink(os.path.join(path,file)))
            except OSError:
              pass
          return path
      except:
        pass
    return None

  #----------------------------------------------------------------------------
  # --- Machine generic utilities

  # --- For g95
  def findg95libroot(self):
    # --- Find the lib root for g95
    # --- Get the full name of the g95 executable
    g95 = os.path.join(self.findfile('g95',followlinks=0),'g95')
    # --- Run it with the appropriate option to return the library path name
    ff = os.popen(g95+' -print-libgcc-file-name')
    gcclib = ff.readline()[:-1]
    ff.close()
    # --- Strip off the gcc library name
    libroot = os.path.dirname(gcclib)
    # --- That's it!
    return libroot

  #-----------------------------------------------------------------------------
  # --- LINUX
  def linux_intel8(self):
    if (self.findfile('ifort') and
        (self.fcompname=='intel8' or self.fcompname is None)):
      self.fcompname = 'ifort'
      # --- Intel8
      self.f90free  = 'ifort -nofor_main -free -r8 -DIFC -fpp -Zp8 -fPIC'
      self.f90fixed = 'ifort -nofor_main -132 -r8 -DIFC -fpp -Zp8 -fPIC'
      if self.implicitnone:
        self.f90free  += ' -implicitnone'
        self.f90fixed += ' -implicitnone'
      self.popt = '-O'
      flibroot,b = os.path.split(self.findfile('ifort'))
      self.libdirs = [flibroot+'/lib']
      self.libs = ['ifcore','ifport','imf','svml','cxa','irc','unwind']
      cpuinfo = open('/proc/cpuinfo','r').read()
      if re.search('Pentium III',cpuinfo):
        self.fopt = '-O3 -xK -tpp6 -ip -unroll -prefetch'
      elif re.search('AMD Athlon',cpuinfo):
        self.fopt = '-O3 -ip -unroll -prefetch'
      elif self.processor == 'ia64':
        self.fopt = '-O3 -ip -unroll -tpp2'
        # --- The IA64 is needed for top.h - ISZ must be 8.
        self.f90free = self.f90free + ' -fpic -DIA64 -i8'
        self.f90fixed = self.f90fixed + ' -fpic -DIA64 -i8'
        self.libs.remove('svml')
      elif struct.calcsize('l') == 8:
        self.fopt = '-O3 -xW -tpp7 -ip -unroll -prefetch'
        self.f90free = self.f90free + ' -DISZ=8 -i8'
        self.f90fixed = self.f90fixed + ' -DISZ=8 -i8'
      else:
        self.fopt = '-O3 -xN -tpp7 -ip -unroll -prefetch'
      return 1

  def linux_intel(self):
    if (self.findfile('ifc') and
        (self.fcompname=='intel' or self.fcompname is None)):
      self.fcompname = 'ifc'
      # --- Intel
      self.f90free  = 'ifc -132 -r8 -DIFC -fpp -C90 -Zp8'
      self.f90fixed = 'ifc -132 -r8 -DIFC -fpp -C90 -Zp8'
      if self.implicitnone:
        self.f90free  += ' -implicitnone'
        self.f90fixed += ' -implicitnone'
      self.popt = '-O'
      flibroot,b = os.path.split(self.findfile('ifc'))
      self.libdirs = [flibroot+'/lib']
      self.libs = ['IEPCF90','CEPCF90','F90','intrins','imf','svml','irc','cxa']
      cpuinfo = open('/proc/cpuinfo','r').read()
      if re.search('Pentium III',cpuinfo):
        self.fopt = '-O3 -xK -tpp6 -ip -unroll -prefetch'
      elif re.search('AMD Athlon',cpuinfo):
        self.fopt = '-O3 -ip -unroll -prefetch'
      else:
        self.fopt = '-O3 -xW -tpp7 -ip -unroll -prefetch'
      return 1

  def linux_g95(self):
    if (self.findfile('g95') and
        (self.fcompname=='g95' or self.fcompname is None)):
      self.fcompname = 'g95'
      self.f90free  = 'g95 -ffree-form -r8 -fPIC -Wno=155 -fshort-circuit'
      self.f90fixed = 'g95 -ffixed-line-length-132 -r8 -fPIC -fshort-circuit'
      if self.implicitnone:
        self.f90free  += ' -fimplicit-none'
        self.f90fixed += ' -fimplicit-none'
      self.popt = '-O'
      self.forthonargs = ['--2underscores']
      flibroot = self.findg95libroot()
      self.libdirs = [flibroot]
      self.libs = ['f95']
      cpuinfo = open('/proc/cpuinfo','r').read()
      if re.search('Pentium III',cpuinfo):
        self.fopt = '-O3'
      elif re.search('AMD Athlon',cpuinfo):
        self.fopt = '-O3'
      elif struct.calcsize('l') == 8:
        self.fopt = '-O3 -mfpmath=sse -ftree-vectorize -ftree-vectorizer-verbose=5 -funroll-loops -fstrict-aliasing -fsched-interblock -falign-loops=16 -falign-jumps=16 -falign-functions=16 -ffast-math -fstrict-aliasing'
        self.f90free = self.f90free + ' -DISZ=8 -i8'
        self.f90fixed = self.f90fixed + ' -DISZ=8 -i8'
      else:
        self.fopt = '-O3'
      return 1

  def linux_pg(self):
    if (self.findfile('pgf90') and
        (self.fcompname=='pg' or self.fcompname is None)):
      self.fcompname = 'pgi'
      # --- Portland group
      self.f90free  = 'pgf90 -Mextend -Mdclchk -r8'
      self.f90fixed = 'pgf90 -Mextend -Mdclchk -r8'
      self.popt = '-Mcache_align'
      flibroot,b = os.path.split(self.findfile('pgf90'))
      self.libdirs = [flibroot+'/lib']
      self.libs = ['pgf90'] # ???
      self.fopt = '-fast -Mcache_align'
      return 1

  def linux_absoft(self):
    if (self.findfile('f90') and
        (self.fcompname=='absoft' or self.fcompname is None)):
      self.fcompname = 'absoft'
      # --- Absoft
      self.f90free  = 'f90 -B108 -N113 -W132 -YCFRL=1 -YEXT_NAMES=ASIS'
      self.f90fixed = 'f90 -B108 -N113 -W132 -YCFRL=1 -YEXT_NAMES=ASIS'
      self.forthonargs = ['--2underscores']
      flibroot,b = os.path.split(self.findfile('f90'))
      self.libdirs = [flibroot+'/lib']
      self.libs = ['U77','V77','f77math','f90math','fio']
      self.fopt = '-O'
      return 1

  def linux_lahey(self):
    if (self.findfile('lf95') and
        (self.fcompname=='lahey' or self.fcompname is None)):
      self.fcompname = 'lahey'
      # --- Lahey
      # in = implicit none
      # dbl = real*8 (variables or constants?)
      # [n]fix = fixed or free form
      # wide = column width longer than 72
      # ap = preserve arithmetic precision
      self.f90free  = 'lf95 --nfix --dbl --mlcdecl'
      self.f90fixed = 'lf95 --fix --wide --dbl --mlcdecl'
      if self.implicitnone:
        self.f90free  += ' --in'
        self.f90fixed += ' --in'
      self.popt = '-O'
      flibroot,b = os.path.split(self.findfile('lf95'))      
      self.libdirs = [flibroot+'/lib']
      self.libs = ["fj9i6","fj9f6","fj9e6","fccx86"]
      cpuinfo = open('/proc/cpuinfo','r').read()
      if re.search('Pentium III',cpuinfo):
        self.fopt = '--O2 --unroll --prefetch --nap --npca --ntrace --nsav'
      elif re.search('AMD Athlon',cpuinfo):
        self.fopt = '--O2 --unroll --prefetch --nap --npca --ntrace --nsav'
      else:
        self.fopt = '--O2 --unroll --prefetch --nap --npca --ntrace --nsav'
      return 1

  def linux_pathscale(self):
    if ((self.findfile('pathf90') or self.findfile('pathf95')) and
        self.fcompname in [None,'pathf90','pathf95','pathscale']):
      if self.findfile('pathf95'): self.fcompname = 'pathf95'
      else:                        self.fcompname = 'pathf90'
      # --- Intel8
      self.f90free  = self.fcompname + ' -freeform -r8 -DPATHF90 -ftpp -fPIC -woff1615 -fno-second-underscore'
      self.f90fixed = self.fcompname + ' -fixedform -extend_source -r8 -DPATHF90 -ftpp -fPIC -woff1615 -fno-second-underscore'
      self.popt = '-O'
      flibroot,b = os.path.split(self.findfile(self.fcompname))
      self.libdirs = [flibroot+'/lib/2.1']
      self.libs = ['pathfortran']
      cpuinfo = open('/proc/cpuinfo','r').read()
      self.extra_compile_args = ['-fPIC']
      self.extra_link_args = ['-fPIC']
      if re.search('Pentium III',cpuinfo):
        self.fopt = '-Ofast'
      elif re.search('AMD Athlon',cpuinfo):
        self.fopt = '-O3'
      elif struct.calcsize('l') == 8:
        self.fopt = '-O3 -OPT:Ofast -fno-math-errno'
        self.f90free = self.f90free + ' -DISZ=8 -i8'
        self.f90fixed = self.f90fixed + ' -DISZ=8 -i8'
      else:
        self.fopt = '-Ofast'
      return 1

  #-----------------------------------------------------------------------------
  # --- CYGWIN
  def cygwin_g95(self):
    if (self.findfile('g95') and
        (self.fcompname=='g95' or self.fcompname is None)):
      self.fcompname = 'g95'
      # --- g95
      self.f90free  = 'g95 -r8'
      self.f90fixed = 'g95 -r8 -ffixed-line-length-132'
      self.forthonargs = ['--2underscores']
      self.fopt = '-O3 -ftree-vectorize -ftree-vectorizer-verbose=5'
#      self.fopt = '-O3 -funroll-loops -fstrict-aliasing -fsched-interblock  \
#           -falign-loops=16 -falign-jumps=16 -falign-functions=16 \
#           -falign-jumps-max-skip=15 -falign-loops-max-skip=15 -malign-natural \
#           -ffast-math -mpowerpc-gpopt -force_cpusubtype_ALL \
#           -fstrict-aliasing'
#      self.extra_link_args = ['-flat_namespace','-undefined suppress','-lg2c']
      self.extra_link_args = ['-flat_namespace','--allow-shlib-undefined','-Wl,--export-all-symbols','-Wl,-export-dynamic','-Wl,--unresolved-symbols=ignore-all','-lg2c']
      flibroot = self.findg95libroot()
      self.libdirs = [flibroot,'/lib/w32api']
      self.libs = ['f95']
      return 1

  #-----------------------------------------------------------------------------
  # --- MAC OSX
  def macosx_g95(self):
    if (self.findfile('g95') and
        (self.fcompname=='g95' or self.fcompname is None)):
      self.fcompname = 'g95'
      # --- g95
      self.f90free  = 'g95 -r8 -fzero -ffree-form -Wno=155'
      self.f90fixed = 'g95 -r8 -fzero -ffixed-line-length-132'
      if self.implicitnone:
        self.f90free  += ' -fimplicit-none'
        self.f90fixed += ' -fimplicit-none'
      self.forthonargs = ['--2underscores']
      self.fopt = '-O3 -funroll-loops -fstrict-aliasing -fsched-interblock  \
           -falign-loops=16 -falign-jumps=16 -falign-functions=16 \
           -malign-natural -ftree-vectorize -ftree-vectorizer-verbose=5 \
           -ffast-math -mpowerpc-gpopt -force_cpusubtype_ALL \
           -fstrict-aliasing -mtune=G5 -mcpu=G5 -mpowerpc64'
#      self.fopt = '-O3  -mtune=G5 -mcpu=G5 -mpowerpc64'
      self.extra_link_args = ['-flat_namespace']
      flibroot = self.findg95libroot()
      self.libdirs = [flibroot]
      self.libs = ['f95']
      return 1

  def macosx_gfortran(self):
    if (self.findfile('gfortran') and
        (self.fcompname=='gfortran' or self.fcompname is None)):
      self.fcompname = 'gfortran'
#      print "WARNING: This compiler might cause a bus error."
      # --- gfortran
      self.f90free  = 'gfortran -fdefault-real-8 -fdefault-double-8'
      self.f90fixed = 'gfortran -fdefault-real-8 -fdefault-double-8 -ffixed-line-length-132'
      self.forthonargs = ['--2underscores']
      flibroot,b = os.path.split(self.findfile('gfortran'))
      self.fopt = '-O3 -funroll-loops -fstrict-aliasing -fsched-interblock  \
           -falign-loops=16 -falign-jumps=16 -falign-functions=16 \
           -malign-natural \
           -ffast-math -mpowerpc-gpopt -force_cpusubtype_ALL \
           -fstrict-aliasing -mtune=G5 -mcpu=G5 -mpowerpc64'
#      self.fopt = '-O3  -mtune=G5 -mcpu=G5 -mpowerpc64'
      self.fopt = '-O3'
      self.extra_link_args = ['-flat_namespace','-lg2c']
      self.libdirs = [flibroot+'/lib','/usr/local/gfortran/lib']
      self.libs = ['gfortran']
      return 1

  def macosx_xlf(self):
    if (self.findfile('xlf90') and
        (self.fcompname in ['xlf','xlf90'] or self.fcompname is None)):
      self.fcompname = 'xlf'
      # --- XLF
      self.f90free  = 'xlf95 -WF,-DXLF -qsuffix=f=f90:cpp=F90 -qextname -qintsize=4 -qdpc=e -bmaxdata:0x70000000 -bmaxstack:0x10000000 -qinitauto'
      self.f90fixed = 'xlf95 -WF,-DXLF -qextname -qfixed=132 -qintsize=4 -qdpc=e -bmaxdata:0x70000000 -bmaxstack:0x10000000 -qinitauto'
      if self.implicitnone:
        self.f90free  += ' -u'
        self.f90fixed += ' -u'
      self.fopt = '-O5'
#      self.fopt = '-O1'
      #self.f90free  = 'xlf95 -qsuffix=f=F90'
      #self.f90fixed = 'xlf95 -qsuffix=f=F90'
      self.extra_link_args = ['-flat_namespace']#,'-Wl,-undefined,suppress']#,'-Wl,-stack_size,10000000']
      flibroot,b = os.path.split(self.findfile('xlf95'))
      self.libdirs = [flibroot+'/lib']
      self.libs = ['xlf90','xl','xlfmath']
      return 1

  def macosx_absoft(self):
    if (self.findfile('f90') and
        (self.fcompname=='absoft' or self.fcompname is None)):
      self.fcompname = 'absoft'
      print 'compiler is ABSOFT!'
      # --- Absoft
      self.f90free  = 'f90 -N11 -N113 -YEXT_NAMES=LCS -YEXT_SFX=_'
      self.f90fixed = 'f90 -f fixed -W 132 -N11 -N113 -YEXT_NAMES=LCS -YEXT_SFX=_'
#      self.f90free  = 'f90 -ffree -YEXT_NAMES=LCS -YEXT_SFX=_'
#      self.f90fixed = 'f90 -ffixed -W 132 -YEXT_NAMES=LCS -YEXT_SFX=_'
      flibroot,b = os.path.split(self.findfile('f90'))
      self.libdirs = [flibroot+'/lib']
      self.extra_link_args = ['-flat_namespace','-Wl,-undefined,suppress']
      self.libs = ['fio','f77math','f90math','f90math_altivec','lapack','blas']
      self.fopt = '-O3'
      return 1

  def macosx_nag(self):
    if (self.findfile('f95') and
        (self.fcompname=='nag' or self.fcompname is None)):
      self.fcompname = 'nag'
      # --- NAG
      self.f90free  = 'f95 -132 -fpp -Wp,-macro=no_com -Wc,-O3 -Wc,-funroll-loops -free -PIC -u -w -mismatch_all -kind=byte -r8'
      self.f90fixed = 'f95 -132 -fpp -u -Wp,-macro=no_com -Wp,-fixed -fixed -Wc,-O3 -Wc,-funroll-loops -PIC -w -mismatch_all -kind=byte -r8'
      self.f90free  = 'f95 -132 -fpp -Wp,-macro=no_com -free -PIC -u -w -mismatch_all -kind=byte -r8 -Oassumed=contig'
      self.f90fixed = 'f95 -132 -fpp -Wp,-macro=no_com -Wp,-fixed -fixed -PIC -u -w -mismatch_all -kind=byte -r8 -Oassumed=contig'
      flibroot,b = os.path.split(self.findfile('f95'))
      self.extra_link_args = ['-flat_namespace','-framework vecLib','/usr/local/lib/NAGWare/quickfit.o','/usr/local/lib/NAGWare/libf96.a']
      self.libs = ['m']
      self.fopt = '-Wc,-O3 -Wc,-funroll-loops -O3 -Ounroll=2'
      self.fopt = '-O4 -Wc,-fast'
      self.fopt = '-O3 '#-Wc,-fast'
      self.define_macros.append(('NAG','1'))
      return 1

  def macosx_gnu(self):
    if (self.findfile('g95') and
        (self.fcompname=='gnu' or self.fcompname is None)):
      self.fcompname = 'gnu'
      # --- GNU
      self.f90free  = 'f95 -132 -fpp -Wp,-macro=no_com -free -PIC -w -mismatch_all -kind=byte -r8'
      self.f90fixed = 'f95 -132 -fpp -Wp,-macro=no_com -Wp,-fixed -fixed -PIC -w -mismatch_all -kind=byte -r8'
      self.f90free  = 'g95 -r8'
      self.f90fixed = 'g95 -r8 -ffixed-form -ffixed-line-length-132'
      flibroot,b = os.path.split(self.findfile('g95'))
      self.libdirs = [flibroot+'/lib']
      self.libs = ['???']
      self.fopts = '-O3'
      return 1

  #-----------------------------------------------------------------------------
  # --- WIN32
  def win32_pg(self):
    if (self.findfile('pgf90') and
        (self.fcompname=='pg' or self.fcompname is None)):
      self.fcompname = 'pgi'
      # --- Portland group
      self.f90free  = 'pgf90 -Mextend -Mdclchk -r8'
      self.f90fixed = 'pgf90 -Mextend -Mdclchk -r8'
      self.popt = '-Mcache_align'
      flibroot,b = os.path.split(self.findfile('pgf90'))
      self.libdirs = [flibroot+'/Lib']
      self.libs = ['???']
      self.fopt = '-fast -Mcache_align'
      return 1

  def win32_intel(self):
    if (self.findfile('ifl') and
        (self.fcompname=='intel' or self.fcompname is None)):
      self.fcompname = 'ifl'
      # --- Intel
      self.f90free  = 'ifl -Qextend_source -Qautodouble -DIFC -FR -Qfpp -4Yd -C90 -Zp8 -Qlowercase -us -MT -Zl -static'
      self.f90fixed = 'ifl -Qextend_source -Qautodouble -DIFC -FI -Qfpp -4Yd -C90 -Zp8 -Qlowercase -us -MT -Zl -static'
      flibroot,b = os.path.split(self.findfile('ifl'))
      self.libdirs = [flibroot+'/Lib']
      self.libs = ['CEPCF90MD','F90MD','intrinsMD']
      self.fopt = '-O3'
      return 1

  #-----------------------------------------------------------------------------
  # --- AIX
  def aix_xlf(self):
    if (self.fcompname=='xlf' or
        (self.fcompname is None and self.findfile('xlf95'))):
      self.fcompname = 'xlf'
      # --- IBM SP, serial
      self.f90free  = 'xlf95 -c -WF,-DXLF -qmaxmem=8192 -qdpc=e -qintsize=4 -qsave=defaultinit -qsuffix=f=f90:cpp=F90 -qfree=f90 -bmaxdata:0x70000000 -bmaxstack:0x10000000 -WF,-DESSL'
      self.f90fixed = 'xlf95 -c -WF,-DXLF -qmaxmem=8192 -qdpc=e -qintsize=4 -qsave=defaultinit -qfixed=132 -bmaxdata:0x70000000 -bmaxstack:0x10000000 -WF,-DESSL'
      self.popt = '-O'
      if struct.calcsize('l') == 4:
        self.extra_link_args = ['-bmaxdata:0x70000000','-bmaxstack:0x10000000']
        self.extra_compile_args = ['-bmaxdata:0x70000000','-bmaxstack:0x10000000']
        self.ld = 'xlf -bmaxdata:0x70000000 -bmaxstack:0x10000000 -bE:$(PYTHON)/lib/python$(PYVERS)/config/python.exp'
      elif struct.calcsize('l') == 8:
        self.f90free  = 'xlf95_r -q64 -WF,-DISZ=8 -c -WF,-DXLF -qmaxmem=8192 -qdpc=e -qintsize=8 -qsave=defaultinit -qsuffix=f=f90:cpp=F90 -qfree=f90 -WF,-DESSL'
        self.f90fixed = 'xlf95_r -q64 -WF,-DISZ=8 -c -WF,-DXLF -qmaxmem=8192 -qdpc=e -qintsize=8 -qsave=defaultinit -qfixed=132 -WF,-DESSL'
        self.extra_link_args = ['-q64'] #,'-qheapdebug','-qcheck=all']
        self.extra_compile_args = ['-q64'] #,'-qheapdebug','-qcheck=all']
        self.ld = 'xlf_r -q64 -bE:$(PYTHON)/lib/python$(PYVERS)/config/python.exp'
      if self.implicitnone:
        self.f90free  += ' -u'
        self.f90fixed += ' -u'
      self.libs = ['xlf90','xlopt','xlf','xlomp_ser','pthread','essl']
      self.fopt = '-O3 -qstrict -qarch=pwr3 -qtune=pwr3'
      return 1

  def aix_mpxlf(self):
    if (self.fcompname=='mpxlf' or
        (self.fcompname is None and self.findfile('mpxlf95'))):
      self.fcompname = 'xlf'
      # --- IBM SP, parallel
      self.f90free  = 'mpxlf95 -c -WF,-DXLF -qmaxmem=8192 -qdpc=e -qintsize=4 -qsave=defaultinit -WF,-DMPIPARALLEL -qsuffix=f=f90:cpp=F90 -qfree=f90 -bmaxdata:0x70000000 -bmaxstack:0x10000000 -WF,-DESSL'
      self.f90fixed = 'mpxlf95 -c -WF,-DXLF -qmaxmem=8192 -qdpc=e -qintsize=4 -qsave=defaultinit -WF,-DMPIPARALLEL -qfixed=132 -bmaxdata:0x70000000 -bmaxstack:0x10000000 -WF,-DESSL'
      if self.implicitnone:
        self.f90free  += ' -u'
        self.f90fixed += ' -u'
      self.popt = '-O'
      self.extra_link_args = ['-bmaxdata:0x70000000','-bmaxstack:0x10000000']
      self.extra_compile_args = ['-bmaxdata:0x70000000','-bmaxstack:0x10000000']
      self.ld = 'mpxlf_r -bmaxdata:0x70000000 -bmaxstack:0x10000000 -bE:$(PYTHON)/lib/python$(PYVERS)/config/python.exp'
      self.libs = ['xlf90','xlopt','xlf','xlomp_ser','pthread','essl']
     #self.libs = ' $(PYMPI)/driver.o $(PYMPI)/patchedmain.o -L$(PYMPI) -lpympi -lpthread'
      self.defines = ['PYMPI=/usr/common/homes/g/grote/pyMPI']
      self.fopt = '-O3 -qstrict -qarch=pwr3 -qtune=pwr3'
      return 1

  def aix_xlf_r(self):
    if (self.fcompname=='xlf_r' or
        (self.fcompname is None and self.findfile('xlf95_r'))):
      self.fcompname = 'xlf'
      # --- IBM SP, OpenMP
      self.f90free  = 'xlf95_r -c -WF,-DXLF -qmaxmem=8192 -qdpc=e -qintsize=4 -qsave=defaultinit -qsuffix=f=f90:cpp=F90 -qfree=f90 -bmaxdata:0x70000000 -bmaxstack:0x10000000 -WF,-DESSL'
      self.f90fixed = 'xlf95 -c -WF,-DXLF -qmaxmem=8192 -qdpc=e -qintsize=4 -qsave=defaultinit -qfixed=132 -bmaxdata:0x70000000 -bmaxstack:0x10000000 -WF,-DESSL'
      if self.implicitnone:
        self.f90free  += ' -u'
        self.f90fixed += ' -u'
      self.popt = '-O'
      self.extra_link_args = ['-bmaxdata:0x70000000','-bmaxstack:0x10000000']
      self.extra_compile_args = ['-bmaxdata:0x70000000','-bmaxstack:0x10000000']
      self.ld = 'xlf95_r -bmaxdata:0x70000000 -bmaxstack:0x10000000 -bE:$(PYTHON)/lib/python$(PYVERS)/config/python.exp'
      #self.libs = ['pthread','xlf90','xlopt','xlf','xlsmp']
      self.libs = ['xlf90','xlopt','xlf','xlsmp','pthreads','essl']
      self.fopt = '-O3 -qstrict -qarch=pwr3 -qtune=pwr3 -qsmp=omp'
      return 1

  def aix_mpxlf64(self):
    if (self.fcompname=='mpxlf64' or
        (self.fcompname is None and self.findfile('mpxlf95'))):
      self.fcompname = 'xlf'
      # --- IBM SP, parallel
      self.f90free  = 'mpxlf95_r -c -q64 -WF,-DISZ=8 -WF,-DXLF -qmaxmem=8192 -qdpc=e -qintsize=8 -qsave=defaultinit -WF,-DMPIPARALLEL -qsuffix=f=f90:cpp=F90 -qfree=f90 -WF,-DESSL'
      self.f90fixed = 'mpxlf95_r -c -q64 -WF,-DISZ=8 -WF,-DXLF -qmaxmem=8192 -qdpc=e -qintsize=8 -qsave=defaultinit -WF,-DMPIPARALLEL -qfixed=132 -WF,-DESSL'
      if self.implicitnone:
        self.f90free  += ' -u'
        self.f90fixed += ' -u'
      self.popt = '-O'
      self.extra_link_args = ['-q64']
      self.extra_compile_args = ['-q64']
      self.ld = 'mpxlf95_r -q64 -bE:$(PYTHON)/lib/python$(PYVERS)/config/python.exp'
      self.libs = ['xlf90','xlopt','xlf','xlomp_ser','pthread','essl']
     #self.libs = ' $(PYMPI)/driver.o $(PYMPI)/patchedmain.o -L$(PYMPI) -lpympi -lpthread'
      self.defines = ['PYMPI=/usr/common/homes/g/grote/pyMPI']
      self.fopt = '-O3 -qstrict -qarch=pwr3 -qtune=pwr3'
      return 1

  def aix_pghpf(self):
    if (self.findfile('pghpf') and
        (self.fcompname=='pghpf' or self.fcompname is None)):
      self.fcompname = 'pghpf'
      # --- Portland group
      self.f90free  = 'pghpf -Mextend -Mdclchk -r8'
      self.f90fixed = 'pghpf -Mextend -Mdclchk -r8'
      self.popt = '-Mcache_align'
      flibroot,b = os.path.split(self.findfile('pghpf'))
      self.libdirs = [flibroot+'/lib']
      self.libs = ['pghpf'] # ???
      self.fopt = '-fast -Mcache_align'
      return 1

