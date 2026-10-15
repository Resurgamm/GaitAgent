#!/usr/bin/env bash
set -x  # print the commands

export MASTER_PORT=${MASTER_PORT:-12330}  # You should set the same master_port in all the nodes

OUTPUT_DIR='YOUR_PATH/work_dir/child_gait_ft'  # Your output folder for deepspeed config file, logs and checkpoints
DATA_PATH='YOUR_PATH/data'  # The data list folder. the folder has three files: train.csv, val.csv, test.csv
DATA_ROOT='YOUR_PATH/data'  # The data root folder. the folder has the video files.
MODEL_PATH='YOUR_PATH/models/vit_g_hybrid_pt_1200e_k710_ft.pth'  # Model for initializing parameters

GPUS_PER_NODE=${GPUS_PER_NODE:-4}  # Number of GPUs in each node
PY_ARGS=${@:1}  # Other training args

# Please refer to `run_class_finetuning.py` for the meaning of the following hyperreferences
OMP_NUM_THREADS=1 python -m torch.distributed.launch --nproc_per_node=${GPUS_PER_NODE} \
        --master_port ${MASTER_PORT} --nnodes=1 --node_rank=0 --master_addr=127.0.0.1 \
        run_class_finetuning.py \
        --model vit_giant_patch14_224 \
        --data_set MyDataset \
        --nb_classes 2 \
        --data_path ${DATA_PATH} \
        --data_root ${DATA_ROOT} \
        --finetune ${MODEL_PATH} \
        --log_dir ${OUTPUT_DIR} \
        --output_dir ${OUTPUT_DIR} \
        --batch_size 2 \
        --input_size 224 \
        --short_side_size 224 \
        --save_ckpt_freq 10 \
        --num_frames 32 \
        --sampling_rate 2 \
        --num_sample 1 \
        --num_workers 10 \
        --opt adamw \
        --lr 1e-4 \
        --drop_path 0.1 \
        --clip_grad 5.0 \
        --layer_decay 0.9 \
        --opt_betas 0.9 0.999 \
        --weight_decay 0.05 \
        --warmup_epochs 3 \
        --epochs 20 \
        --dist_eval \
        --model_key 'model|module|state_dict' \
        --enable_wandb \
        --wandb_project 'YOUR_WANDB_PROJECT' \
        --wandb_run_name 'YOUR_RUN_NAME' \
        --with_checkpoint \
        --use_bbox_masking \
        --patch_size 14 \
        ${PY_ARGS}