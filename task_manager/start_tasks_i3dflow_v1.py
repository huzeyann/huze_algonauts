import itertools

from clearml import Task

PROJECT_NAME = 'Algonauts i3d_flow V1'
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

schs = ['old_mix', 'detach_aux']
rois = ['V1', 'V2', 'V3', 'V4']
layers = ['x1,x2,x3,x4', 'x2,x3,x4', 'x3', 'x2,x3']
ps = [
    [[3, 5],
     [3, 5],
     [3, 5],
     [3, 5]],
]
for roi in rois:
    for layer in layers:
        for p in ps:
            for sch in schs:
                queue = next(queues_buffer)

                p_text = ''
                for pp in p:
                    p_text += '-'.join([str(i) for i in pp])
                    p_text += ','

                tags = [roi, layer, p_text, sch]
                cloned_task = Task.clone(source_task=template_task,
                                         name=','.join(tags),
                                         parent=template_task.id)

                cloned_task.add_tags(tags)

                cloned_task_parameters = cloned_task.get_parameters()
                # cloned_task_parameters['rois'] = [roi]
                cloned_task_parameters['Args/rois'] = roi
                cloned_task_parameters['Args/track'] = 'mini_track'
                cloned_task_parameters['Args/video_size'] = 256
                cloned_task_parameters['Args/crop_size'] = 224
                cloned_task_parameters['Args/video_frames'] = 64
                # cloned_task_parameters['Args/batch_size'] = 32 if pooling_sch in ['avg', 'max'] else 24
                cloned_task_parameters['Args/learning_rate'] = 1e-4
                cloned_task_parameters['Args/batch_size'] = 8
                cloned_task_parameters['Args/accumulate_grad_batches'] = 4
                cloned_task_parameters['Args/num_layers'] = 2
                cloned_task_parameters['Args/conv_size'] = 256
                cloned_task_parameters['Args/first_layer_hidden'] = 2048
                cloned_task_parameters['Args/layer_hidden'] = 2048
                cloned_task_parameters['Args/debug'] = False
                cloned_task_parameters['Args/fp16'] = False
                cloned_task_parameters['Args/freeze_bn'] = True
                cloned_task_parameters['Args/detach_aux'] = True if sch == 'detach_aux' else False
                cloned_task_parameters['Args/old_mix'] = True if sch == 'old_mix' else False
                cloned_task_parameters['Args/reduce_aux_loss_ratio'] = -1 if sch == 'old_mix' else 0.7
                cloned_task_parameters['Args/reduce_aux_patience'] = 2
                cloned_task_parameters['Args/separate_rois'] = True
                cloned_task_parameters['Args/early_stop_epochs'] = 6
                cloned_task_parameters['Args/max_epochs'] = 100
                cloned_task_parameters['Args/backbone_freeze_epochs'] = 100
                cloned_task_parameters['Args/gpus'] = queue.split('-')[1]
                # cloned_task_parameters['Args/x1_pooling_mode'] = 'spp'
                cloned_task_parameters['Args/pooling_mode'] = 'avg'
                for i, l in enumerate('x1,x2,x3,x4'.split(',')):
                    cloned_task_parameters[f'Args/{l}_pooling_mode'] = 'spp'
                    cloned_task_parameters[f'Args/spp_size_{l}'] = p[i]
                    cloned_task_parameters[f'Args/spp_size_t_{l}'] = [1 for _ in range(len(p[i]))]
                cloned_task_parameters['Args/backbone_type'] = 'i3d_flow'
                cloned_task_parameters['Args/load_from_np'] = True
                cloned_task_parameters['Args/final_fusion'] = 'conv' if sch == 'detach_aux' else 'concat'
                cloned_task_parameters['Args/pyramid_layers'] = layer
                cloned_task_parameters['Args/pathways'] = 'none'
                cloned_task_parameters['Args/aux_loss_weight'] = 1 if sch == 'detach_aux' else 0
                cloned_task_parameters['Args/val_check_interval'] = 0.5
                cloned_task_parameters['Args/val_ratio'] = 0.1
                cloned_task_parameters['Args/save_checkpoints'] = True
                cloned_task_parameters['Args/predictions_dir'] = f'/data_smr/huze/projects/my_algonauts/predictions/'

                cloned_task.set_parameters(cloned_task_parameters)
                print('Experiment set with parameters {}'.format(cloned_task_parameters))

                # enqueue the task for execution
                Task.enqueue(cloned_task.id, queue_name=queue)
                print('Experiment id={} enqueue for execution'.format(cloned_task.id))

                task_ids.append(cloned_task.id)


schs = ['old_mix', 'detach_aux']
rois = ['EBA', 'LOC', 'FFA', 'PPA', 'STS']
layers = ['x1,x2,x3,x4', 'x2,x3,x4', 'x3', 'x4', 'x3,x4']
ps = [
    [[3, 5],
     [1, 3, 4],
     [1, 3, 6],
     [1, 3, 6]],
]
for roi in rois:
    for layer in layers:
        for p in ps:
            for sch in schs:
                queue = next(queues_buffer)

                p_text = ''
                for pp in p:
                    p_text += '-'.join([str(i) for i in pp])
                    p_text += ','

                tags = [roi, layer, p_text, sch]
                cloned_task = Task.clone(source_task=template_task,
                                         name=','.join(tags),
                                         parent=template_task.id)

                cloned_task.add_tags(tags)

                cloned_task_parameters = cloned_task.get_parameters()
                # cloned_task_parameters['rois'] = [roi]
                cloned_task_parameters['Args/rois'] = roi
                cloned_task_parameters['Args/track'] = 'mini_track'
                cloned_task_parameters['Args/video_size'] = 256
                cloned_task_parameters['Args/crop_size'] = 224
                cloned_task_parameters['Args/video_frames'] = 64
                # cloned_task_parameters['Args/batch_size'] = 32 if pooling_sch in ['avg', 'max'] else 24
                cloned_task_parameters['Args/learning_rate'] = 1e-4
                cloned_task_parameters['Args/batch_size'] = 8
                cloned_task_parameters['Args/accumulate_grad_batches'] = 4
                cloned_task_parameters['Args/num_layers'] = 2
                cloned_task_parameters['Args/conv_size'] = 256
                cloned_task_parameters['Args/first_layer_hidden'] = 2048
                cloned_task_parameters['Args/layer_hidden'] = 2048
                cloned_task_parameters['Args/debug'] = False
                cloned_task_parameters['Args/fp16'] = False
                cloned_task_parameters['Args/freeze_bn'] = True
                cloned_task_parameters['Args/detach_aux'] = True if sch == 'detach_aux' else False
                cloned_task_parameters['Args/old_mix'] = True if sch == 'old_mix' else False
                cloned_task_parameters['Args/reduce_aux_loss_ratio'] = -1 if sch == 'old_mix' else 0.7
                cloned_task_parameters['Args/reduce_aux_patience'] = 2
                cloned_task_parameters['Args/separate_rois'] = True
                cloned_task_parameters['Args/early_stop_epochs'] = 6
                cloned_task_parameters['Args/max_epochs'] = 100
                cloned_task_parameters['Args/backbone_freeze_epochs'] = 100
                cloned_task_parameters['Args/gpus'] = queue.split('-')[1]
                # cloned_task_parameters['Args/x1_pooling_mode'] = 'spp'
                cloned_task_parameters['Args/pooling_mode'] = 'avg'
                for i, l in enumerate('x1,x2,x3,x4'.split(',')):
                    cloned_task_parameters[f'Args/{l}_pooling_mode'] = 'spp'
                    cloned_task_parameters[f'Args/spp_size_{l}'] = p[i]
                    cloned_task_parameters[f'Args/spp_size_t_{l}'] = [1 for _ in range(len(p[i]))]
                cloned_task_parameters['Args/backbone_type'] = 'i3d_flow'
                cloned_task_parameters['Args/load_from_np'] = True
                cloned_task_parameters['Args/final_fusion'] = 'conv' if sch == 'detach_aux' else 'concat'
                cloned_task_parameters['Args/pyramid_layers'] = layer
                cloned_task_parameters['Args/pathways'] = 'none'
                cloned_task_parameters['Args/aux_loss_weight'] = 1 if sch == 'detach_aux' else 0
                cloned_task_parameters['Args/val_check_interval'] = 0.5
                cloned_task_parameters['Args/val_ratio'] = 0.1
                cloned_task_parameters['Args/save_checkpoints'] = True
                cloned_task_parameters['Args/predictions_dir'] = f'/data_smr/huze/projects/my_algonauts/predictions/'

                cloned_task.set_parameters(cloned_task_parameters)
                print('Experiment set with parameters {}'.format(cloned_task_parameters))

                # enqueue the task for execution
                Task.enqueue(cloned_task.id, queue_name=queue)
                print('Experiment id={} enqueue for execution'.format(cloned_task.id))

                task_ids.append(cloned_task.id)


schs = ['detach_aux']
rois = ['EBA', 'LOC', 'FFA', 'PPA', 'STS']
layers = ['x5', 'x4']
ps = [
    [[3, 5],
     [1, 3],
     [1, 2, 3],
     [1, 2, 3]],
]
for roi in rois:
    for layer in layers:
        for p in ps:
            for sch in schs:
                queue = next(queues_buffer)

                p_text = ''
                for pp in p:
                    p_text += '-'.join([str(i) for i in pp])
                    p_text += ','

                tags = [roi, layer, p_text, sch, '1024']
                cloned_task = Task.clone(source_task=template_task,
                                         name=','.join(tags),
                                         parent=template_task.id)

                cloned_task.add_tags(tags)

                cloned_task_parameters = cloned_task.get_parameters()
                # cloned_task_parameters['rois'] = [roi]
                cloned_task_parameters['Args/rois'] = roi
                cloned_task_parameters['Args/track'] = 'mini_track'
                cloned_task_parameters['Args/video_size'] = 256
                cloned_task_parameters['Args/crop_size'] = 224
                cloned_task_parameters['Args/video_frames'] = 64
                # cloned_task_parameters['Args/batch_size'] = 32 if pooling_sch in ['avg', 'max'] else 24
                cloned_task_parameters['Args/learning_rate'] = 1e-4
                cloned_task_parameters['Args/batch_size'] = 8
                cloned_task_parameters['Args/accumulate_grad_batches'] = 4
                cloned_task_parameters['Args/num_layers'] = 2
                cloned_task_parameters['Args/conv_size'] = 1024
                cloned_task_parameters['Args/first_layer_hidden'] = 2048
                cloned_task_parameters['Args/layer_hidden'] = 2048
                cloned_task_parameters['Args/debug'] = False
                cloned_task_parameters['Args/fp16'] = False
                cloned_task_parameters['Args/freeze_bn'] = True
                cloned_task_parameters['Args/detach_aux'] = True if sch == 'detach_aux' else False
                cloned_task_parameters['Args/old_mix'] = True if sch == 'old_mix' else False
                cloned_task_parameters['Args/reduce_aux_loss_ratio'] = -1 if sch == 'old_mix' else 0.7
                cloned_task_parameters['Args/reduce_aux_patience'] = 2
                cloned_task_parameters['Args/separate_rois'] = True
                cloned_task_parameters['Args/early_stop_epochs'] = 6
                cloned_task_parameters['Args/max_epochs'] = 100
                cloned_task_parameters['Args/backbone_freeze_epochs'] = 100
                cloned_task_parameters['Args/gpus'] = queue.split('-')[1]
                # cloned_task_parameters['Args/x1_pooling_mode'] = 'spp'
                cloned_task_parameters['Args/pooling_mode'] = 'avg'
                for i, l in enumerate('x1,x2,x3,x4'.split(',')):
                    cloned_task_parameters[f'Args/{l}_pooling_mode'] = 'spp'
                    cloned_task_parameters[f'Args/spp_size_{l}'] = p[i]
                    cloned_task_parameters[f'Args/spp_size_t_{l}'] = [1 for _ in range(len(p[i]))]
                cloned_task_parameters['Args/backbone_type'] = 'i3d_flow'
                cloned_task_parameters['Args/load_from_np'] = True
                cloned_task_parameters['Args/final_fusion'] = 'conv' if sch == 'detach_aux' else 'concat'
                cloned_task_parameters['Args/pyramid_layers'] = layer
                cloned_task_parameters['Args/pathways'] = 'none'
                cloned_task_parameters['Args/aux_loss_weight'] = 1 if sch == 'detach_aux' else 0
                cloned_task_parameters['Args/val_check_interval'] = 0.5
                cloned_task_parameters['Args/val_ratio'] = 0.1
                cloned_task_parameters['Args/save_checkpoints'] = True
                cloned_task_parameters['Args/predictions_dir'] = f'/data_smr/huze/projects/my_algonauts/predictions/'

                cloned_task.set_parameters(cloned_task_parameters)
                print('Experiment set with parameters {}'.format(cloned_task_parameters))

                # enqueue the task for execution
                Task.enqueue(cloned_task.id, queue_name=queue)
                print('Experiment id={} enqueue for execution'.format(cloned_task.id))

                task_ids.append(cloned_task.id)


print(task_ids)
