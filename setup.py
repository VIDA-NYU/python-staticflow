import io
import os
from setuptools import setup


# pip workaround
os.chdir(os.path.abspath(os.path.dirname(__file__)))


# Need to specify encoding for PY3, which has the worst unicode handling ever
with io.open('README.rst', encoding='utf-8') as fp:
    description = fp.read()
setup(name='staticflow',
      version='0.1',
      packages=['staticflow'],
      description="Construct a data flow from static analysis of Python code",
      author="Remi Rampin",
      author_email='remirampin@gmai.com',
      maintainer="Remi Rampin",
      maintainer_email='remirampin@gmail.com',
      url='http://github.com/VIDA-NYU/python-staticflow',
      long_description=description,
      license='BSD-3-Clause',
      keywords=['python', 'analysis', 'ast', 'dataflow', 'flow', 'provenance',
                'dependencies', 'vida', 'nyu'],
      classifiers=[
          'Development Status :: 1 - Planning',
          'Intended Audience :: Developers',
          'Intended Audience :: Science/Research',
          'License :: OSI Approved :: BSD License',
          'Operating System :: OS Independent',
          'Programming Language :: Python :: 2.7',
          'Topic :: Scientific/Engineering',
          'Topic :: Software Development'])
