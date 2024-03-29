# Analysis of voxel-based 3D object detection methods efficiency for real-time embedded systems

This is a code that allows to reproduce results of the [Analysis of voxel-based 3D object detection methods efficiency for real-time embedded systems](https://arxiv.org/abs/2105.10316) paper.

The training configurations for PointPillars and TANet models can be found in `pointpillars_with_TANet/second/configs/{pointpillars|tanet}/car/near_far/`

Our code is based on [TANet](https://github.com/happinesslz/TANet), which is based on [PointPillars](https://github.com/nutonomy/second.pytorch) and [SECOND](https://github.com/traveller59/second.pytorch).

Video, describing results of the paper can be found [here](https://youtu.be/HeCXapfFDg0).

If you use this work for your research, you can cite it as:
```
@INPROCEEDINGS{oleksiienko2021voxel3od,
  author={Oleksiienko, Illia and Iosifidis, Alexandros},
  booktitle={2021 International Conference on Emerging Techniques in Computational Intelligence (ICETCI)}, 
  title={Analysis of voxel-based 3D object detection methods efficiency for real-time embedded systems}, 
  year={2021},
  pages={59-64}
}
```
