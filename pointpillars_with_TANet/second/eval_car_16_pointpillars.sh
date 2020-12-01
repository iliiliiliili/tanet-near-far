#! /bin/bash
#python create_data.py create_kitti_info_file --data_path=/mnt/data2/Kitti/object
#python create_data.py create_reduced_point_cloud --data_path=/mnt/data2/Kitti/object
#python create_data.py create_groundtruth_database --data_path=/mnt/data2/Kitti/object

CUDA_VISIBLE_DEVICES=1 python ./pytorch/train.py evaluate --config_path=./configs/pointpillars/car/xyres_16.proto --model_dir=/home/io3/TANet/pointpillars_with_TANet/train_16_car_pointpillars
