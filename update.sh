#!/bin/bash

#pip3 install --ignore-installed -r dev-requirements.txt -e .
#python3 setup.py build
#python3 setup.py install
#pip3 install --ignore-installed --upgrade .
pip3 install -r dev-requirements.txt -e .
python3 setup.py js
python3 setup.py css
python3 setup.py build
python3 setup.py install
pip3 install --upgrade .
