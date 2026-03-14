
=======================================
 Tower Defense Game by Inspired Python
=======================================

Welcome to the *Inspired Python* Tower Defense Game demo. This demo encompasses all the concepts you'll read and learn about in the main course.

You can find the full course here::

   https://www.inspiredpython.com/course/create-tower-defense-game/make-your-own-tower-defense-game-with-pygame


This zip file is distributed as a functional Python package. That means you can install it like a normal Python package, though we recommend you do so in a Python virtual environment. (You can read more about how to do this in the course.)

Packages needed
===============

Ubuntu: ``libsdl2-dev`` and ``libsdl2-2.0-0`` for pygame. Ensure the ``tkinter`` package is also installed. For instance, ``python-3.10-tk``, for Python 3.10.

Mac / Windows: You must ensure ``tkinter`` is selected during the installation.

(Optional) Creating a virtual environment
=========================================

*This is one way of doing it; we encourage you to consult the Python virtualenv documentation for more advanced setups.*

1. Change to the directory you unzipped the files to.
2. Create a virtualenv::

     python -m venv .env

  You can use a name other than ``.env``.
3. Go into the directory structure and activate it

   Windows::

     cd .env\scripts\
     activate

   Linux::

     cd .env/bin/
     . activate

You can now safely install packages without interfering with your primary Python installation.


Running the demo
================

If you want to dive right in, you can, by installing it::

    python -m pip install .

Then, to run it::

    python -m tower.main launch

If you want to make modifications to the demo code and quickly test them, you should install it in *editable* mode *instead* of installing it::

    python -m pip install --editable .


NOTE: If you see any errors about not being able to write to certain directories, like ``site-packages``, you must use a virtual environment or run the code as admin or root. We strongly urge you to use a virtualenv environment though!

Playing the demo
================

Done right, you should see a main menu appear. You can play a demo level included with the game by pressing ``Play`` and navigating to ``tower/assets/levels`` and opening ``demo.json``.

- You can place turrets by pressing ``1``.

  You can only place up to the number allowed in the HUD, which is by default 1, and it increases as you kill enemies.

- You can use ``Q`` and ``E`` to rotate the direction the turret should sweep for enemies.

Map Editing
===========

1. You can save or load levels in map editing mode with ``F5`` and ``F9`` respectively.
2. You can pick and place assets by pressing ``1``, ``2``, ``3``, and ``5``.

   a. ``1`` through ``3`` place graphical assets. ``5`` places an enemy at the cursor position. If there is a valid path for it to travel in map editing mode, it will snap to that point and try to find its way to the exit.
   b. The mouse wheel will cycle through assets.
   c. ``Q`` and ``E`` rotates the sprite
   d. Right-clicking with a selected asset cancels that selection.
   e. If there is no selected asset, the asset(s) under the cursor are instead deleted.
3. You can enable debug overlays with ``F1`` (show path finding) ``F2`` (show collision mask).

