# Setup
conda deactivate
conda create --name cpegen python=3.11
conda activate cpegen
conda install -c conda-forge -n cpegen ipykernel ipywidgets --update-deps --force-reinstall
conda install -c conda-forge -n cpegen numpy pandas transformers datasets --update-deps
conda install -c conda-forge -c pytorch -c nvidia -n cpegen pytorch torchvision torchaudio pytorch-cuda=12.1 --update-deps 
/C/DEVEL/software/miniconda3/envs/cpegen/python.exe -m pip install --upgrade pip
pip install tensorflow 
pip install transformers[torch]
pip freeze > requirements.txt
conda env export --no-builds | grep -v "^prefix: " > environment.yml
