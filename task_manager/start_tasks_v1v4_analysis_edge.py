import itertools

from clearml import Task

PROJECT_NAME = 'Algonauts V1V4 analysis'
BASE_TASK = 'task template'

task = Task.init(project_name=PROJECT_NAME,
                 task_name='Task Manager',
                 task_type=Task.TaskTypes.optimizer,
                 reuse_last_task_id=False)

template_task = Task.get_task(project_name=PROJECT_NAME,
                              task_name=BASE_TASK)

available_devices = {
    '16': [0, 1],
}

queue_names = []
for k, vs in available_devices.items():
    for v in vs:
        queue_names.append(f'{k}-{v}')
queues_buffer = itertools.cycle(queue_names)

task_ids = []


def start_tasks_spp(rois, layers, ps, freeze_bns, pooling_modes, batch_size=32):
    for roi in rois:
        for layer in layers:
            for p in ps:
                for freeze_bn in freeze_bns:
                    for pooling_mode in pooling_modes:
                        assert pooling_mode in ['max', 'avg']
                        queue = next(queues_buffer)

                        p_text = '-'.join([str(i) for i in p])
                        freeze_text = 'f_bn' if freeze_bn else 'nof_bn'
                        pooling_text = f'spp_{p_text}_{pooling_mode}'

                        tags = [roi, layer, pooling_text, freeze_text]
                        cloned_task = Task.clone(source_task=template_task,
                                                 name=','.join(tags),
                                                 parent=template_task.id)

                        cloned_task.add_tags(tags)

                        cloned_task_parameters = cloned_task.get_parameters()
                        # cloned_task_parameters['rois'] = [roi]
                        cloned_task_parameters['Args/rois'] = roi
                        cloned_task_parameters['Args/track'] = 'mini_track'
                        cloned_task_parameters['Args/video_size'] = 128
                        cloned_task_parameters['Args/crop_size'] = 0
                        cloned_task_parameters['Args/video_frames'] = 4
                        cloned_task_parameters['Args/backbone_type'] = 'bdcn_edge'
                        cloned_task_parameters['Args/preprocessing_type'] = 'bdcn'
                        cloned_task_parameters['Args/load_from_np'] = False
                        cloned_task_parameters['Args/learning_rate'] = 1e-4
                        cloned_task_parameters['Args/step_lr_epochs'] = [4]
                        cloned_task_parameters['Args/step_lr_ratio'] = 0.7
                        cloned_task_parameters['Args/batch_size'] = batch_size if not freeze_bn else 8
                        cloned_task_parameters['Args/accumulate_grad_batches'] = 1 if not freeze_bn else int(
                            batch_size / 8)
                        cloned_task_parameters['Args/num_layers'] = 1
                        cloned_task_parameters['Args/conv_size'] = 256
                        cloned_task_parameters['Args/first_layer_hidden'] = 2048
                        cloned_task_parameters['Args/layer_hidden'] = 2048
                        cloned_task_parameters['Args/debug'] = False
                        cloned_task_parameters['Args/fp16'] = True
                        cloned_task_parameters['Args/freeze_bn'] = freeze_bn
                        cloned_task_parameters['Args/old_mix'] = True
                        cloned_task_parameters['Args/early_stop_epochs'] = 5
                        cloned_task_parameters['Args/max_epochs'] = 100
                        cloned_task_parameters['Args/backbone_lr_ratio'] = 0.5
                        cloned_task_parameters['Args/backbone_freeze_epochs'] = 4
                        cloned_task_parameters['Args/gpus'] = queue.split('-')[1]
                        cloned_task_parameters['Args/pooling_mode'] = 'max'
                        cloned_task_parameters['Args/spp'] = True
                        cloned_task_parameters['Args/spp_size'] = p
                        cloned_task_parameters['Args/val_check_interval'] = 1.0
                        cloned_task_parameters['Args/val_ratio'] = 0.1
                        cloned_task_parameters['Args/save_checkpoints'] = True
                        cloned_task_parameters['Args/rm_checkpoints'] = False
                        cloned_task_parameters['Args/checkpoints_dir'] = '/mnt/v1v4/ckpts/'
                        cloned_task_parameters[
                            'Args/predictions_dir'] = f'/data_smr/huze/projects/my_algonauts/predictions/'

                        cloned_task.set_parameters(cloned_task_parameters)
                        print('Experiment set with parameters {}'.format(cloned_task_parameters))

                        # enqueue the task for execution
                        Task.enqueue(cloned_task.id, queue_name=queue)
                        print('Experiment id={} enqueue for execution'.format(cloned_task.id))

                        task_ids.append(cloned_task.id)

start_tasks_spp(
    rois=['EBA', 'LOC', 'PPA', 'FFA', 'STS'],
    layers=['x3'],
    ps=[
        [3, 6, 9],
    ],
    freeze_bns=[True],
    pooling_modes=['avg'],
    batch_size=24
)


print(task_ids)
