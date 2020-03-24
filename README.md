# Carla-synthetic-dataset-generation
Creating synthetic dataset for training 3D bbox module

Inspired from https://github.com/AlanNaoto/carla-dataset-runner

# Setup pre requisites

* Step1: 
  Python carla package and its dependencies.
  Follow this guide to install Carla via github.
  https://carla.readthedocs.io/en/latest/start_quickstart/

* Step2: 
  Clone this repo.
  For other dependencies (to run data capturing scripts), use the requirements.txt 

* Step3:
  Setup the python path for the carla egg file.
  Open the [settings.py](settings.py) file and change the carla egg path to your own.

# Running

* step1: Launch CarlaEU4
```
if you downloaded the carla pre-compiled package, navigate to the folder, open a terminal and: 
```
  ./CarlaUE4.sh TownXX -opengl 

* step2: Launch data capturing
```
Navigate to the folder where the repo is cloned, open a terminal and: 
```
  python3 main.py -ve 100 -wa 110 

# Data captured



