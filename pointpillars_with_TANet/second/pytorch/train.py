import os
import pathlib
import pickle
import shutil
import time
from functools import partial

import fire
import numpy as np
import torch
from google.protobuf import text_format
from tensorboardX import SummaryWriter

import torchplus
import second.data.kitti_common as kitti
from second.builder import target_assigner_builder, voxel_builder
from second.data.preprocess import merge_second_batch
from second.protos import pipeline_pb2
from second.pytorch.builder import (
    box_coder_builder,
    input_reader_builder,
    lr_scheduler_builder,
    optimizer_builder,
    second_builder,
)
from second.utils.eval import get_coco_eval_result, get_official_eval_result
from second.utils.progress_bar import ProgressBar
from metrics import AverageMetric, Metric, RangeMetric
from second.core import box_np_ops
from pytorch.core import box_torch_ops

def _get_pos_neg_loss(cls_loss, labels):
    # cls_loss: [N, num_anchors, num_class]
    # labels: [N, num_anchors]
    batch_size = cls_loss.shape[0]
    if cls_loss.shape[-1] == 1 or len(cls_loss.shape) == 2:
        cls_pos_loss = (labels > 0).type_as(cls_loss) * cls_loss.view(
            batch_size, -1
        )
        cls_neg_loss = (labels == 0).type_as(cls_loss) * cls_loss.view(
            batch_size, -1
        )
        cls_pos_loss = cls_pos_loss.sum() / batch_size
        cls_neg_loss = cls_neg_loss.sum() / batch_size
    else:
        cls_pos_loss = cls_loss[..., 1:].sum() / batch_size
        cls_neg_loss = cls_loss[..., 0].sum() / batch_size
    return cls_pos_loss, cls_neg_loss


def _flat_nested_json_dict(json_dict, flatted, sep=".", start=""):
    for k, v in json_dict.items():
        if isinstance(v, dict):
            _flat_nested_json_dict(v, flatted, sep, start + sep + k)
        else:
            flatted[start + sep + k] = v


def flat_nested_json_dict(json_dict, sep=".") -> dict:
    """flat a nested json-like dict. this function make shadow copy.
    """
    flatted = {}
    for k, v in json_dict.items():
        if isinstance(v, dict):
            _flat_nested_json_dict(v, flatted, sep, k)
        else:
            flatted[k] = v
    return flatted


def example_convert_to_torch(
    example, dtype=torch.float32, device=None
) -> dict:
    device = device or torch.device("cuda:0")
    example_torch = {}
    float_names = [
        "voxels",
        "anchors",
        "reg_targets",
        "reg_weights",
        "bev_map",
        "rect",
        "Trv2c",
        "P2",
        "gt_boxes",
    ]

    for k, v in example.items():
        if k in float_names:
            example_torch[k] = torch.as_tensor(v, dtype=dtype, device=device)
        elif k in ["coordinates", "labels", "num_points"]:
            example_torch[k] = torch.as_tensor(
                v, dtype=torch.int32, device=device
            )
        elif k in ["anchors_mask"]:
            example_torch[k] = torch.as_tensor(
                v, dtype=torch.uint8, device=device
            )
        else:
            example_torch[k] = v
    return example_torch


def train(
    config_path,
    model_dir,
    result_path=None,
    create_folder=False,
    display_step=50,
    summary_step=5,
    pickle_result=True,
    refine_weight=2,
):
    """train a VoxelNet model specified by a config file.
    """
    if create_folder:
        if pathlib.Path(model_dir).exists():
            model_dir = torchplus.train.create_folder(model_dir)

    model_dir = pathlib.Path(model_dir)
    model_dir.mkdir(parents=True, exist_ok=True)
    eval_checkpoint_dir = model_dir / "eval_checkpoints"
    eval_checkpoint_dir.mkdir(parents=True, exist_ok=True)
    if result_path is None:
        result_path = model_dir / "results"
    config_file_bkp = "pipeline.config"
    config = pipeline_pb2.TrainEvalPipelineConfig()
    with open(config_path, "r") as f:
        proto_str = f.read()
        text_format.Merge(proto_str, config)
    shutil.copyfile(config_path, str(model_dir / config_file_bkp))
    input_cfg = config.train_input_reader
    eval_input_cfg = config.eval_input_reader
    model_cfg = config.model.second
    train_cfg = config.train_config

    class_names = list(input_cfg.class_names)
    ######################
    # BUILD VOXEL GENERATOR
    ######################
    voxel_generator = voxel_builder.build(model_cfg.voxel_generator)
    ######################
    # BUILD TARGET ASSIGNER
    ######################
    bv_range = voxel_generator.point_cloud_range[[0, 1, 3, 4]]
    box_coder = box_coder_builder.build(model_cfg.box_coder)
    target_assigner_cfg = model_cfg.target_assigner
    target_assigner = target_assigner_builder.build(
        target_assigner_cfg, bv_range, box_coder
    )
    ######################
    # BUILD NET
    ######################
    center_limit_range = model_cfg.post_center_limit_range
    net = second_builder.build(model_cfg, voxel_generator, target_assigner)
    net.cuda()
    # net_train = torch.nn.DataParallel(net).cuda()
    print("num_trainable parameters:", len(list(net.parameters())))
    for n, p in net.named_parameters():
        print(n, p.shape)
    ######################
    # BUILD OPTIMIZER
    ######################
    # we need global_step to create lr_scheduler, so restore net first.
    torchplus.train.try_restore_latest_checkpoints(model_dir, [net])
    gstep = net.get_global_step() - 1
    optimizer_cfg = train_cfg.optimizer
    if train_cfg.enable_mixed_precision:
        net.half()
        net.metrics_to_float()
        net.convert_norm_to_float(net)
    optimizer = optimizer_builder.build(optimizer_cfg, net.parameters())
    if train_cfg.enable_mixed_precision:
        loss_scale = train_cfg.loss_scale_factor
        mixed_optimizer = torchplus.train.MixedPrecisionWrapper(
            optimizer, loss_scale
        )
    else:
        mixed_optimizer = optimizer
    # must restore optimizer AFTER using MixedPrecisionWrapper
    torchplus.train.try_restore_latest_checkpoints(
        model_dir, [mixed_optimizer]
    )
    lr_scheduler = lr_scheduler_builder.build(optimizer_cfg, optimizer, gstep)
    if train_cfg.enable_mixed_precision:
        float_dtype = torch.float16
    else:
        float_dtype = torch.float32
    ######################
    # PREPARE INPUT
    ######################

    dataset = input_reader_builder.build(
        input_cfg,
        model_cfg,
        training=True,
        voxel_generator=voxel_generator,
        target_assigner=target_assigner,
    )
    eval_dataset = input_reader_builder.build(
        eval_input_cfg,
        model_cfg,
        training=False,
        voxel_generator=voxel_generator,
        target_assigner=target_assigner,
    )

    def _worker_init_fn(worker_id):
        time_seed = np.array(time.time(), dtype=np.int32)
        np.random.seed(time_seed + worker_id)
        print(f"WORKER {worker_id} seed:", np.random.get_state()[1][0])

    dataloader = torch.utils.data.DataLoader(
        dataset,
        batch_size=input_cfg.batch_size,
        shuffle=True,
        num_workers=input_cfg.num_workers,
        pin_memory=False,
        collate_fn=merge_second_batch,
        worker_init_fn=_worker_init_fn,
    )
    eval_dataloader = torch.utils.data.DataLoader(
        eval_dataset,
        batch_size=eval_input_cfg.batch_size,
        shuffle=False,
        num_workers=eval_input_cfg.num_workers,
        pin_memory=False,
        collate_fn=merge_second_batch,
    )
    data_iter = iter(dataloader)

    ######################
    # TRAINING
    ######################
    log_path = model_dir / "log.txt"
    logf = open(log_path, "a")
    logf.write(proto_str)
    logf.write("\n")
    summary_dir = model_dir / "summary"
    summary_dir.mkdir(parents=True, exist_ok=True)
    writer = SummaryWriter(str(summary_dir))

    total_step_elapsed = 0
    remain_steps = train_cfg.steps - net.get_global_step()
    t = time.time()
    ckpt_start_time = t

    total_loop = train_cfg.steps // train_cfg.steps_per_eval + 1
    # total_loop = remain_steps // train_cfg.steps_per_eval + 1
    clear_metrics_every_epoch = train_cfg.clear_metrics_every_epoch

    if train_cfg.steps % train_cfg.steps_per_eval == 0:
        total_loop -= 1
    mixed_optimizer.zero_grad()
    try:
        for _ in range(total_loop):
            if (
                total_step_elapsed + train_cfg.steps_per_eval
                > train_cfg.steps
            ):
                steps = train_cfg.steps % train_cfg.steps_per_eval
            else:
                steps = train_cfg.steps_per_eval
            for step in range(steps):
                lr_scheduler.step()
                try:
                    example = next(data_iter)
                except StopIteration:
                    print("end epoch")
                    if clear_metrics_every_epoch:
                        net.clear_metrics()
                    data_iter = iter(dataloader)
                    example = next(data_iter)
                example_torch = example_convert_to_torch(example, float_dtype)

                batch_size = example["anchors"].shape[0]

                ret_dict = net(example_torch, refine_weight)

                # box_preds = ret_dict["box_preds"]
                cls_preds = ret_dict["cls_preds"]
                loss = ret_dict["loss"].mean()
                cls_loss_reduced = ret_dict["cls_loss_reduced"].mean()
                loc_loss_reduced = ret_dict["loc_loss_reduced"].mean()
                cls_pos_loss = ret_dict["cls_pos_loss"]
                cls_neg_loss = ret_dict["cls_neg_loss"]
                loc_loss = ret_dict["loc_loss"]
                cls_loss = ret_dict["cls_loss"]
                dir_loss_reduced = ret_dict["dir_loss_reduced"]
                cared = ret_dict["cared"]
                labels = example_torch["labels"]
                if train_cfg.enable_mixed_precision:
                    loss *= loss_scale
                loss.backward()
                torch.nn.utils.clip_grad_norm_(net.parameters(), 10.0)
                mixed_optimizer.step()
                mixed_optimizer.zero_grad()
                net.update_global_step()
                net_metrics = net.update_metrics(
                    cls_loss_reduced,
                    loc_loss_reduced,
                    cls_preds,
                    labels,
                    cared,
                )

                step_time = time.time() - t
                t = time.time()
                metrics = {}
                num_pos = int((labels > 0)[0].float().sum().cpu().numpy())
                num_neg = int((labels == 0)[0].float().sum().cpu().numpy())
                if "anchors_mask" not in example_torch:
                    num_anchors = example_torch["anchors"].shape[1]
                else:
                    num_anchors = int(example_torch["anchors_mask"][0].sum())
                global_step = net.get_global_step()
                if global_step % display_step == 0:
                    loc_loss_elem = [
                        float(
                            loc_loss[:, :, i].sum().detach().cpu().numpy()
                            / batch_size
                        )
                        for i in range(loc_loss.shape[-1])
                    ]
                    metrics["step"] = global_step
                    metrics["steptime"] = step_time
                    metrics.update(net_metrics)
                    metrics["loss"] = {}
                    metrics["loss"]["loc_elem"] = loc_loss_elem
                    metrics["loss"]["cls_pos_rt"] = float(
                        cls_pos_loss.detach().cpu().numpy()
                    )
                    metrics["loss"]["cls_neg_rt"] = float(
                        cls_neg_loss.detach().cpu().numpy()
                    )

                    ########################################
                    if (
                        model_cfg.rpn.module_class_name == "PSA"
                        or model_cfg.rpn.module_class_name == "RefineDet"
                    ):
                        coarse_loss = ret_dict["coarse_loss"]
                        refine_loss = ret_dict["refine_loss"]
                        metrics["coarse_loss"] = float(
                            coarse_loss.detach().cpu().numpy()
                        )
                        metrics["refine_loss"] = float(
                            refine_loss.detach().cpu().numpy()
                        )
                    ########################################
                    # if unlabeled_training:
                    #     metrics["loss"]["diff_rt"] = float(
                    #         diff_loc_loss_reduced.detach().cpu().numpy())
                    if model_cfg.use_direction_classifier:
                        metrics["loss"]["dir_rt"] = float(
                            dir_loss_reduced.detach().cpu().numpy()
                        )
                    metrics["num_vox"] = int(example_torch["voxels"].shape[0])
                    metrics["num_pos"] = int(num_pos)
                    metrics["num_neg"] = int(num_neg)
                    metrics["num_anchors"] = int(num_anchors)
                    metrics["lr"] = float(
                        mixed_optimizer.param_groups[0]["lr"]
                    )
                    metrics["image_idx"] = example["image_idx"][0]
                    flatted_metrics = flat_nested_json_dict(metrics)
                    flatted_summarys = flat_nested_json_dict(metrics, "/")
                    for k, v in flatted_summarys.items():
                        if isinstance(v, (list, tuple)):
                            v = {str(i): e for i, e in enumerate(v)}
                            writer.add_scalars(k, v, global_step)
                        else:
                            writer.add_scalar(k, v, global_step)
                    metrics_str_list = []
                    for k, v in flatted_metrics.items():
                        if isinstance(v, float):
                            metrics_str_list.append(f"{k}={v:.3}")
                        elif isinstance(v, (list, tuple)):
                            if v and isinstance(v[0], float):
                                v_str = ", ".join([f"{e:.3}" for e in v])
                                metrics_str_list.append(f"{k}=[{v_str}]")
                            else:
                                metrics_str_list.append(f"{k}={v}")
                        else:
                            metrics_str_list.append(f"{k}={v}")
                    log_str = ", ".join(metrics_str_list)
                    print(log_str, file=logf)
                    print(log_str)
                ckpt_elasped_time = time.time() - ckpt_start_time
                if ckpt_elasped_time > train_cfg.save_checkpoints_secs:
                    torchplus.train.save_models(
                        model_dir, [net, optimizer], net.get_global_step()
                    )
                    ckpt_start_time = time.time()
            total_step_elapsed += steps
            torchplus.train.save_models(
                model_dir, [net, optimizer], net.get_global_step()
            )

            # Ensure that all evaluation points are saved forever
            torchplus.train.save_models(
                eval_checkpoint_dir,
                [net, optimizer],
                net.get_global_step(),
                max_to_keep=100,
            )

            net.eval()
            result_path_step = result_path / f"step_{net.get_global_step()}"
            result_path_step.mkdir(parents=True, exist_ok=True)
            print("#################################")
            print("#################################", file=logf)
            print("# EVAL")
            print("# EVAL", file=logf)
            print("#################################")
            print("#################################", file=logf)
            print("Generate output labels...")
            print("Generate output labels...", file=logf)
            t = time.time()
            if (
                model_cfg.rpn.module_class_name == "PSA"
                or model_cfg.rpn.module_class_name == "RefineDet"
            ):
                dt_annos_coarse = []
                dt_annos_refine = []
                prog_bar = ProgressBar()
                prog_bar.start(
                    len(eval_dataset) // eval_input_cfg.batch_size + 1
                )
                for example in iter(eval_dataloader):
                    example = example_convert_to_torch(example, float_dtype)
                    if pickle_result:
                        coarse, refine = predict_kitti_to_anno(
                            net,
                            example,
                            class_names,
                            center_limit_range,
                            model_cfg.lidar_input,
                            use_coarse_to_fine=True,
                        )
                        dt_annos_coarse += coarse
                        dt_annos_refine += refine
                    else:
                        _predict_kitti_to_file(
                            net,
                            example,
                            result_path_step,
                            class_names,
                            center_limit_range,
                            model_cfg.lidar_input,
                            use_coarse_to_fine=True,
                        )
                    prog_bar.print_bar()
            else:
                dt_annos = []
                prog_bar = ProgressBar()
                prog_bar.start(
                    len(eval_dataset) // eval_input_cfg.batch_size + 1
                )
                for example in iter(eval_dataloader):
                    example = example_convert_to_torch(example, float_dtype)
                    if pickle_result:
                        dt_annos += predict_kitti_to_anno(
                            net,
                            example,
                            class_names,
                            center_limit_range,
                            model_cfg.lidar_input,
                            use_coarse_to_fine=False,
                        )
                    else:
                        _predict_kitti_to_file(
                            net,
                            example,
                            result_path_step,
                            class_names,
                            center_limit_range,
                            model_cfg.lidar_input,
                            use_coarse_to_fine=False,
                        )

                    prog_bar.print_bar()

            sec_per_ex = len(eval_dataset) / (time.time() - t)
            print(f"avg forward time per example: {net.avg_forward_time:.3f}")
            print(
                f"avg postprocess time per example: {net.avg_postprocess_time:.3f}"
            )

            net.clear_time_metrics()
            print(f"generate label finished({sec_per_ex:.2f}/s). start eval:")
            print(
                f"generate label finished({sec_per_ex:.2f}/s). start eval:",
                file=logf,
            )
            gt_annos = [
                info["annos"] for info in eval_dataset.dataset.kitti_infos
            ]
            if not pickle_result:
                dt_annos = kitti.get_label_annos(result_path_step)

            if (
                model_cfg.rpn.module_class_name == "PSA"
                or model_cfg.rpn.module_class_name == "RefineDet"
            ):

                print("Before Refine:")
                (
                    result,
                    mAPbbox,
                    mAPbev,
                    mAP3d,
                    mAPaos,
                ) = get_official_eval_result(
                    gt_annos, dt_annos_coarse, class_names, return_data=True
                )
                print(result, file=logf)
                print(result)
                writer.add_text("eval_result", result, global_step)

                print("After Refine:")
                (
                    result,
                    mAPbbox,
                    mAPbev,
                    mAP3d,
                    mAPaos,
                ) = get_official_eval_result(
                    gt_annos, dt_annos_refine, class_names, return_data=True
                )
                dt_annos = dt_annos_refine
            else:
                (
                    result,
                    mAPbbox,
                    mAPbev,
                    mAP3d,
                    mAPaos,
                ) = get_official_eval_result(
                    gt_annos, dt_annos, class_names, return_data=True
                )
            print(result, file=logf)
            print(result)
            writer.add_text("eval_result", result, global_step)

            for i, class_name in enumerate(class_names):
                writer.add_scalar(
                    "bev_ap:{}".format(class_name),
                    mAPbev[i, 1, 0],
                    global_step,
                )
                writer.add_scalar(
                    "3d_ap:{}".format(class_name), mAP3d[i, 1, 0], global_step
                )
                writer.add_scalar(
                    "aos_ap:{}".format(class_name),
                    mAPaos[i, 1, 0],
                    global_step,
                )
            writer.add_scalar(
                "bev_map", np.mean(mAPbev[:, 1, 0]), global_step
            )
            writer.add_scalar("3d_map", np.mean(mAP3d[:, 1, 0]), global_step)
            writer.add_scalar(
                "aos_map", np.mean(mAPaos[:, 1, 0]), global_step
            )

            result = get_coco_eval_result(gt_annos, dt_annos, class_names)
            print(result, file=logf)
            print(result)
            if pickle_result:
                with open(result_path_step / "result.pkl", "wb") as f:
                    pickle.dump(dt_annos, f)
            writer.add_text("eval_result", result, global_step)
            net.train()
    except Exception as e:
        torchplus.train.save_models(
            model_dir, [net, optimizer], net.get_global_step()
        )
        logf.close()
        raise e
    # save model before exit
    torchplus.train.save_models(
        model_dir, [net, optimizer], net.get_global_step()
    )
    logf.close()


def comput_kitti_output(
    predictions_dicts,
    batch_image_shape,
    lidar_input,
    center_limit_range,
    class_names,
    global_set,
):
    annos = []
    for i, preds_dict in enumerate(predictions_dicts):
        image_shape = batch_image_shape[i]
        img_idx = preds_dict["image_idx"]
        if preds_dict["bbox"] is not None:
            box_2d_preds = preds_dict["bbox"].detach().cpu().numpy()
            box_preds = preds_dict["box3d_camera"].detach().cpu().numpy()
            scores = preds_dict["scores"].detach().cpu().numpy()
            box_preds_lidar = preds_dict["box3d_lidar"].detach().cpu().numpy()
            # write pred to file
            label_preds = preds_dict["label_preds"].detach().cpu().numpy()
            # label_preds = np.zeros([box_2d_preds.shape[0]], dtype=np.int32)
            anno = kitti.get_start_result_anno()
            num_example = 0
            for box, box_lidar, bbox, score, label in zip(
                box_preds, box_preds_lidar, box_2d_preds, scores, label_preds
            ):
                if not lidar_input:
                    if bbox[0] > image_shape[1] or bbox[1] > image_shape[0]:
                        continue
                    if bbox[2] < 0 or bbox[3] < 0:
                        continue
                # print(img_shape)
                if center_limit_range is not None:
                    limit_range = np.array(center_limit_range)
                    if np.any(box_lidar[:3] < limit_range[:3]) or np.any(
                        box_lidar[:3] > limit_range[3:]
                    ):
                        continue
                bbox[2:] = np.minimum(bbox[2:], image_shape[::-1])
                bbox[:2] = np.maximum(bbox[:2], [0, 0])
                anno["name"].append(class_names[int(label)])
                anno["truncated"].append(0.0)
                anno["occluded"].append(0)
                anno["alpha"].append(
                    -np.arctan2(-box_lidar[1], box_lidar[0]) + box[6]
                )
                anno["bbox"].append(bbox)
                anno["dimensions"].append(box[3:6])
                anno["location"].append(box[:3])
                anno["rotation_y"].append(box[6])
                if global_set is not None:
                    for i in range(100000):
                        if score in global_set:
                            score -= 1 / 100000
                        else:
                            global_set.add(score)
                            break
                anno["score"].append(score)

                num_example += 1
            if num_example != 0:
                anno = {n: np.stack(v) for n, v in anno.items()}
                annos.append(anno)
            else:
                annos.append(kitti.empty_result_anno())
        else:
            annos.append(kitti.empty_result_anno())
        num_example = annos[-1]["name"].shape[0]
        annos[-1]["image_idx"] = np.array(
            [img_idx] * num_example, dtype=np.int64
        )

    return annos


def predict_kitti_to_anno(
    net,
    example,
    class_names,
    center_limit_range=None,
    lidar_input=False,
    use_coarse_to_fine=True,
    global_set=None,
    fps_metric=None,
):
    batch_image_shape = example["image_shape"]
    batch_imgidx = example["image_idx"]

    if use_coarse_to_fine:

        tt = time.perf_counter()

        predictions_dicts_coarse, predictions_dicts_refine = net(example)

        tt = time.perf_counter() - tt
        fps = 1.0 / tt

        print("fps:", fps, end="\t")
        if fps_metric is not None:
            fps_metric.update(fps)

        # t = time.time()
        annos_coarse = comput_kitti_output(
            predictions_dicts_coarse,
            batch_image_shape,
            lidar_input,
            center_limit_range,
            class_names,
            global_set,
        )
        annos_refine = comput_kitti_output(
            predictions_dicts_refine,
            batch_image_shape,
            lidar_input,
            center_limit_range,
            class_names,
            global_set,
        )
        return annos_coarse, annos_refine
    else:

        tt = time.perf_counter()

        predictions_dicts_coarse = net(example)

        tt = time.perf_counter() - tt
        fps = 1.0 / tt

        print("fps:", fps, end="\t")
        if fps_metric is not None:
            fps_metric.update(fps)

        annos_coarse = comput_kitti_output(
            predictions_dicts_coarse,
            batch_image_shape,
            lidar_input,
            center_limit_range,
            class_names,
            global_set,
        )

        return annos_coarse


def _predict_kitti_to_file(
    net,
    example,
    result_save_path,
    class_names,
    center_limit_range=None,
    lidar_input=False,
    use_coarse_to_fine=True,
    fps_metric=None,
):
    batch_image_shape = example["image_shape"]
    batch_imgidx = example["image_idx"]
    if use_coarse_to_fine:
        _, predictions_dicts_refine = net(example)
        predictions_dicts = predictions_dicts_refine
    else:
        predictions_dicts = net(example)
    # t = time.time()
    for i, preds_dict in enumerate(predictions_dicts):
        image_shape = batch_image_shape[i]
        img_idx = preds_dict["image_idx"]
        if preds_dict["bbox"] is not None:
            box_2d_preds = preds_dict["bbox"].data.cpu().numpy()
            box_preds = preds_dict["box3d_camera"].data.cpu().numpy()
            scores = preds_dict["scores"].data.cpu().numpy()
            box_preds_lidar = preds_dict["box3d_lidar"].data.cpu().numpy()
            # write pred to file
            box_preds = box_preds[
                :, [0, 1, 2, 4, 5, 3, 6]
            ]  # lhw->hwl(label file format)
            label_preds = preds_dict["label_preds"].data.cpu().numpy()
            # label_preds = np.zeros([box_2d_preds.shape[0]], dtype=np.int32)
            result_lines = []
            for box, box_lidar, bbox, score, label in zip(
                box_preds, box_preds_lidar, box_2d_preds, scores, label_preds
            ):
                if not lidar_input:
                    if bbox[0] > image_shape[1] or bbox[1] > image_shape[0]:
                        continue
                    if bbox[2] < 0 or bbox[3] < 0:
                        continue
                # print(img_shape)
                if center_limit_range is not None:
                    limit_range = np.array(center_limit_range)
                    if np.any(box_lidar[:3] < limit_range[:3]) or np.any(
                        box_lidar[:3] > limit_range[3:]
                    ):
                        continue
                bbox[2:] = np.minimum(bbox[2:], image_shape[::-1])
                bbox[:2] = np.maximum(bbox[:2], [0, 0])
                result_dict = {
                    "name": class_names[int(label)],
                    "alpha": -np.arctan2(-box_lidar[1], box_lidar[0])
                    + box[6],
                    "bbox": bbox,
                    "location": box[:3],
                    "dimensions": box[3:6],
                    "rotation_y": box[6],
                    "score": score,
                }
                result_line = kitti.kitti_result_line(result_dict)
                result_lines.append(result_line)
        else:
            result_lines = []
        result_file = (
            f"{result_save_path}/{kitti.get_image_index_str(img_idx)}.txt"
        )
        result_str = "\n".join(result_lines)
        with open(result_file, "w") as f:
            f.write(result_str)


def evaluate(
    config_path,
    model_dir,
    result_path=None,
    predict_test=False,
    ckpt_path=None,
    ref_detfile=None,
    pickle_result=True,
    evaluation_mode="1/2",  # 1/2: take all ground truth boxes, 1/1: take only gt boxes inside voxel range
    metrics_file_name="eval-metrics.txt",
    gt_limit_range=None, # remove ground truth objects outside of this range
):
    model_dir = pathlib.Path(model_dir)
    if predict_test:
        result_name = "predict_test"
    else:
        result_name = "eval_results"
    if result_path is None:
        result_path = model_dir / result_name
    else:
        result_path = pathlib.Path(result_path)
    config = pipeline_pb2.TrainEvalPipelineConfig()
    with open(config_path, "r") as f:
        proto_str = f.read()
        text_format.Merge(proto_str, config)

    input_cfg = config.eval_input_reader
    model_cfg = config.model.second
    train_cfg = config.train_config
    class_names = list(input_cfg.class_names)
    center_limit_range = model_cfg.post_center_limit_range
    
    if gt_limit_range is None:
        gt_limit_range = center_limit_range
    else:
        center_limit_range = gt_limit_range

    ######################
    # BUILD VOXEL GENERATOR
    ######################
    voxel_generator = voxel_builder.build(model_cfg.voxel_generator)
    bv_range = voxel_generator.point_cloud_range[[0, 1, 3, 4]]
    box_coder = box_coder_builder.build(model_cfg.box_coder)
    target_assigner_cfg = model_cfg.target_assigner
    target_assigner = target_assigner_builder.build(
        target_assigner_cfg, bv_range, box_coder
    )

    net = second_builder.build(model_cfg, voxel_generator, target_assigner)
    net.cuda()
    if train_cfg.enable_mixed_precision:
        net.half()
        net.metrics_to_float()
        net.convert_norm_to_float(net)

    if ckpt_path is None:
        torchplus.train.try_restore_latest_checkpoints(model_dir, [net])
    else:
        torchplus.train.restore(ckpt_path, net)

    eval_dataset = input_reader_builder.build(
        input_cfg,
        model_cfg,
        training=False,
        voxel_generator=voxel_generator,
        target_assigner=target_assigner,
    )
    eval_dataloader = torch.utils.data.DataLoader(
        eval_dataset,
        batch_size=input_cfg.batch_size,
        shuffle=False,
        num_workers=input_cfg.num_workers,
        pin_memory=False,
        collate_fn=merge_second_batch,
    )

    if train_cfg.enable_mixed_precision:
        float_dtype = torch.float16
    else:
        float_dtype = torch.float32

    net.eval()
    result_path_step = result_path / f"step_{net.get_global_step()}"
    result_path_step.mkdir(parents=True, exist_ok=True)
    t = time.time()

    fps_metric = AverageMetric()
    total_time = 0
    total_count = 0

    total_metrics = {}

    empty_coarse = [
        {
            "name": np.array([], dtype=np.float64),
            "truncated": np.array([], dtype=np.float64),
            "occluded": np.array([], dtype=np.float64),
            "alpha": np.array([], dtype=np.float64),
            "bbox": np.zeros((0, 4), dtype=np.float64),
            "dimensions": np.zeros(shape=(0, 3), dtype=np.float64),
            "location": np.zeros(shape=(0, 3), dtype=np.float64),
            "rotation_y": np.array([], dtype=np.float64),
            "score": np.array([], dtype=np.float64),
            "image_idx": np.array([], dtype=np.int64),
        }
    ]
    empty_refine = empty_coarse

    if evaluation_mode == "1/2":
        gt_annos = [
            info["annos"] for info in eval_dataset.dataset.kitti_infos
        ]
    elif evaluation_mode == "1/1":

        ogt_annos = [
            info["annos"] for info in eval_dataset.dataset.kitti_infos
        ]

        gt_annos = []
        ev_limit_range = np.array(gt_limit_range)
        in_range_count = 0
        not_in_range_count = 0

        for info in eval_dataset.dataset.kitti_infos:
            rect = info["calib/R0_rect"]
            Trv2c = info["calib/Tr_velo_to_cam"]
            annos = info["annos"]

            filtered_annos = {}
            keys = annos.keys()

            for key in keys:
                filtered_annos[key] = []

            for i in range(len(annos["location"])):
                loc = annos["location"][i]
                lidar_loc = box_np_ops.camera_to_lidar(loc, rect, Trv2c)
                is_in_range = not (
                    np.any(lidar_loc < ev_limit_range[:3])
                    or np.any(lidar_loc > ev_limit_range[3:])
                )

                if is_in_range or np.all(loc == -1000):
                    in_range_count += 0 if np.all(loc == -1000) else 1
                    for key in keys:
                        filtered_annos[key].append(annos[key][i])
                else:
                    not_in_range_count += 1

            for key in keys:

                if len(filtered_annos[key]) == 0:
                    filtered_annos[key] = np.ones(
                        {
                            "name": [0],
                            "truncated": [0],
                            "occluded": [0],
                            "alpha": [0],
                            "bbox": [0, 4],
                            "dimensions": [0, 3],
                            "location": [0, 3],
                            "rotation_y": [0],
                            "score": [0],
                            "index": [0],
                            "group_ids": [0],
                            "difficulty": [0],
                            "num_points_in_gt": [0],
                        }[key],
                        dtype={
                            "name": np.float64,
                            "truncated": np.float64,
                            "occluded": np.float64,
                            "alpha": np.float64,
                            "bbox": np.float64,
                            "dimensions": np.float64,
                            "location": np.float64,
                            "rotation_y": np.float64,
                            "score": np.float64,
                            "index": np.int32,
                            "group_ids": np.int32,
                            "difficulty": np.int32,
                            "num_points_in_gt": np.int32,
                        }[key],
                    )
                else:
                    filtered_annos[key] = np.array(filtered_annos[key])

            gt_annos.append(filtered_annos)

        print(
            "in_range_count:",
            in_range_count,
            "not_in_range_count:",
            not_in_range_count,
        )

        total_metrics["Objects in range"] = Metric(in_range_count)
        total_metrics["Objects not in range"] = Metric(not_in_range_count)

    if (
        model_cfg.rpn.module_class_name == "PSA"
        or model_cfg.rpn.module_class_name == "RefineDet"
    ):
        dt_annos_coarse = []
        dt_annos_refine = []
        print("Generate output labels...")
        bar = ProgressBar()
        bar.start(len(eval_dataset) // input_cfg.batch_size + 1)
        for example in iter(eval_dataloader):
            example = example_convert_to_torch(example, float_dtype)

            if len(example["voxels"]) < 4:
                print("#", end="\n")
                dt_annos_coarse += empty_coarse
                dt_annos_refine += empty_refine
                continue

            tt = time.perf_counter()

            if pickle_result:
                coarse, refine = predict_kitti_to_anno(
                    net,
                    example,
                    class_names,
                    center_limit_range,
                    model_cfg.lidar_input,
                    use_coarse_to_fine=True,
                    global_set=None,
                    fps_metric=fps_metric,
                )
                dt_annos_coarse += coarse
                dt_annos_refine += refine
            else:
                _predict_kitti_to_file(
                    net,
                    example,
                    result_path_step,
                    class_names,
                    center_limit_range,
                    model_cfg.lidar_input,
                    use_coarse_to_fine=True,
                    fps_metric=fps_metric,
                )

            tt = time.perf_counter() - tt
            total_time += tt
            total_count += 1
            bar.print_bar()

        total_detected_coarse = sum(
            [len(a["alpha"]) for a in dt_annos_coarse]
        )
        total_detected_refine = sum(
            [len(a["alpha"]) for a in dt_annos_refine]
        )

        print()
        print(" || total_detected_coarse:", total_detected_coarse)
        print(" || total_detected_refine:", total_detected_refine)

    else:
        dt_annos = []
        print("Generate output labels...")
        bar = ProgressBar()
        bar.start(len(eval_dataset) // input_cfg.batch_size + 1)
        for example in iter(eval_dataloader):
            example = example_convert_to_torch(example, float_dtype)

            tt = time.perf_counter()

            if pickle_result:
                dt_annos += predict_kitti_to_anno(
                    net,
                    example,
                    class_names,
                    center_limit_range,
                    model_cfg.lidar_input,
                    use_coarse_to_fine=False,
                    global_set=None,
                    fps_metric=fps_metric,
                )
            else:
                _predict_kitti_to_file(
                    net,
                    example,
                    result_path_step,
                    class_names,
                    center_limit_range,
                    model_cfg.lidar_input,
                    use_coarse_to_fine=False,
                    fps_metric=fps_metric,
                )

            tt = time.perf_counter() - tt
            total_time += tt
            total_count += 1
            bar.print_bar()

    sec_per_example = len(eval_dataset) / (time.time() - t)
    print()
    print("fps by total:", total_count / total_time)

    print("net._total_inference_count:", net._total_inference_count)
    print("total_count:", total_count)

    print(f"generate label finished({sec_per_example:.2f}/s). start eval:")

    print(f"avg forward time per example: {net.avg_forward_time:.3f}")
    print(f"avg postprocess time per example: {net.avg_postprocess_time:.3f}")
    if not predict_test:
        # gt_annos = [
        #     info["annos"] for info in eval_dataset.dataset.kitti_infos
        # ]

        print(
            " || total_objects_gt:", sum([len(a["alpha"]) for a in gt_annos])
        )

        if not pickle_result:
            dt_annos = kitti.get_label_annos(result_path_step)

        if (
            model_cfg.rpn.module_class_name == "PSA"
            or model_cfg.rpn.module_class_name == "RefineDet"
        ):
            print("Before Refine:")
            (
                result_coarse,
                mAPbbox_coarse,
                mAPbev_coarse,
                mAP3d_coarse,
                mAPaos_coarse,
            ) = get_official_eval_result(
                gt_annos, dt_annos_coarse, class_names, return_data=True,
            )
            print(result_coarse)

            print("After Refine:")
            (
                result_refine,
                mAPbbox_refine,
                mAPbev_refine,
                mAP3d_refine,
                mAPaos_refine,
            ) = get_official_eval_result(
                gt_annos, dt_annos_refine, class_names, return_data=True,
            )
            print(result_refine)
            # result = get_coco_eval_result(
            #     gt_annos, dt_annos_refine, class_names
            # )
            # dt_annos = dt_annos_refine
            # print(result)

            coarse_3dAP_metrics = {}

            for i, class_name in enumerate(class_names):
                metric = Metric()
                metric.update(
                    [
                        mAP3d_coarse[i, 0, 0],
                        mAP3d_coarse[i, 1, 0],
                        mAP3d_coarse[i, 2, 0],
                    ]
                )
                coarse_3dAP_metrics[
                    "Coarse " + class_name + " 3D APs"
                ] = metric

            refine_3dAP_metrics = {}

            for i, class_name in enumerate(class_names):
                metric = Metric()
                metric.update(
                    [
                        mAP3d_refine[i, 0, 0],
                        mAP3d_refine[i, 1, 0],
                        mAP3d_refine[i, 2, 0],
                    ]
                )
                coarse_3dAP_metrics[
                    "Refine " + class_name + " 3D APs"
                ] = metric

            total_metrics = {
                "FPS": fps_metric,
                "Evaluation Mode": Metric(evaluation_mode),
                **coarse_3dAP_metrics,
                **refine_3dAP_metrics,
                **total_metrics,
            }

            log_metrics(
                model_dir / metrics_file_name, total_metrics,
            )
            log_metrics(
                "console", total_metrics,
            )

        else:
            result, mAPbbox, mAPbev, mAP3d, mAPaos = get_official_eval_result(
                gt_annos, dt_annos, class_names, return_data=True
            )
            print(result)

            result_3dAP_metrics = {}

            for i, class_name in enumerate(class_names):
                metric = Metric()
                metric.update(
                    [mAP3d[i, 0, 0], mAP3d[i, 1, 0], mAP3d[i, 2, 0],]
                )
                result_3dAP_metrics[class_name + " 3D APs"] = metric

            total_metrics = {
                "FPS": fps_metric,
                "Evaluation Mode": Metric(evaluation_mode),
                **result_3dAP_metrics,
                **total_metrics,
            }

            log_metrics(
                model_dir / metrics_file_name, total_metrics,
            )

            log_metrics(
                "console", total_metrics,
            )

        # result = get_coco_eval_result(gt_annos, dt_annos, class_names)
        # print(result)
        # if pickle_result:
        #     with open(result_path_step / "result.pkl", "wb") as f:
        #         pickle.dump(dt_annos, f)


def log_metrics(path: str, metrics):
    for name, metric in metrics.items():
        metric.log(path, name + " | ")


if __name__ == "__main__":
    fire.Fire()
