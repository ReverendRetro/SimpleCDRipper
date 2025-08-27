Step 1: Create the Virtual Environment

First, navigate your terminal to the directory where you saved SimpleCDRipperGUI.py. Create a new virtual environment by running:

`python3 -m venv ripper-env`

This command creates a new folder named ripper-env which will contain a fresh Python installation just for this project.

Step 2: Activate the Virtual Environment

Before you can use the new environment, you need to activate it. In the same terminal, run:

`source ripper-env/bin/activate`

You'll know it's active because your terminal prompt will change to show (ripper-env) at the beginning.

Step 3: Install Dependencies Inside the Environment

Now, with the virtual environment active, install the necessary Python packages. These will be installed inside ripper-env and won't affect your system's Python.

`pip install PyQt6 pyinstaller`

Step 4: Run the Packaging Command

With the dependencies installed, you can now run the PyInstaller command just as before. It will use the Python and libraries from your active virtual environment.

`pyinstaller --onefile --windowed --hidden-import=pkgutil SimpleCDRipper.py`

Step 5: Locate and Run Your Application from the /dist folder
