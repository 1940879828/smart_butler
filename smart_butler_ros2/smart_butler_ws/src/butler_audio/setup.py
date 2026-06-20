from setuptools import find_packages, setup

package_name = 'butler_audio'

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
    description='MOSS microphone capture and speaker playback nodes',
    license='Apache-2.0',
    extras_require={
        'test': [
            'pytest',
        ],
        'sounds': [
            'soundfile>=0.12.0',
            'scipy>=1.7.0',
        ],
        'all': [
            'soundfile>=0.12.0',
            'scipy>=1.7.0',
        ],
    },
    entry_points={
        'console_scripts': [
            'mic_node = butler_audio.mic_node:main',
            'speaker_node = butler_audio.speaker_node:main',
        ],
    },
)
