from setuptools import find_packages, setup

package_name = 'butler_voice'

setup(
    name=package_name,
    version='0.0.0',
    packages=find_packages(exclude=['test']),
    data_files=[
        ('share/ament_index/resource_index/packages',
            ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='taro',
    maintainer_email='1940879828@users.noreply.github.com',
    description='MOSS ASR and TTS voice service clients',
    license='Apache-2.0',
    extras_require={
        'test': [
            'pytest',
        ],
    },
    entry_points={
        'console_scripts': [
            'asr_client = butler_voice.asr_client:main',
            'tts_client = butler_voice.tts_client:main',
        ],
    },
)
