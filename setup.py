from setuptools import setup

setup(
    name='smfc',
    version='3.5.2',
    packages=['smfc'],
    entry_points={
        'console_scripts': [
            'smfc = smfc.cmd:main',
        ]
    }
)
