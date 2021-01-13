// add(workstaton, gpus, minimalGpuMemory, name, script, workdingDir, saveScreen = false)

if (toAdd == null) {

    var toAdd = [];
}

var createTasks = (workstatons = 'any') => {

    const combine = (...params) => {

        const createCombinations = (i, n) => {
            
            const result = [];

            if (i == n) {

                return result;
            }

            params[i].forEach(paramValue => {
               
                const other = createCombinations(i + 1, n);

                other.forEach(combination => {

                    result.push([paramValue, ...combination]); 
                });

                if (other.length == 0) {

                    result.push([paramValue]);
                }
            });

            console.log({result});
            return result;
        };

        return createCombinations (0, params.length);
    }

    const configPaths = [

        ["./configs/pointpillars/ped_cycle/near_far/xyres_16_near_0.5.proto", "ped_cycle_pointpillars_xyres_16_pure", "near-0.5"],
        ["./configs/pointpillars/ped_cycle/near_far/xyres_16_near_0.5.proto", "ped_cycle_pointpillars_xyres_16_pure_2", "near-0.5"],
        ["./configs/pointpillars/ped_cycle/near_far/xyres_16_near_0.5.proto", "ped_cycle_pointpillars_xyres_16_pure_3", "near-0.5"],
        ["./configs/pointpillars/ped_cycle/near_far/xyres_20_near_0.5.proto", "ped_cycle_pointpillars_xyres_20_pure", "near-0.5"],
        ["./configs/pointpillars/ped_cycle/near_far/xyres_24_near_0.5.proto", "ped_cycle_pointpillars_xyres_24_pure", "near-0.5"],
        ["./configs/pointpillars/ped_cycle/near_far/xyres_28_near_0.5.proto", "ped_cycle_pointpillars_xyres_28_pure", "near-0.5"],
        ["./configs/pointpillars/ped_cycle/near_far/xyres_32_near_0.5.proto", "ped_cycle_pointpillars_xyres_32_pure", "near-0.5"],
        ["./configs/pointpillars/ped_cycle/near_far/xyres_48_near_0.5.proto", "ped_cycle_pointpillars_xyres_48_pure", "near-0.5"],
        ["./configs/pointpillars/ped_cycle/near_far/xyres_56_near_0.5.proto", "ped_cycle_pointpillars_xyres_56_pure", "near-0.5"],

        ["./configs/pointpillars/ped_cycle/xyres_16.proto", "ped_cycle_pointpillars_xyres_16_near_0_5_pure", "full-subscene"],
        ["./configs/pointpillars/ped_cycle/xyres_20.proto", "ped_cycle_pointpillars_xyres_20_near_0_5_pure", "full-subscene"],
        ["./configs/pointpillars/ped_cycle/xyres_24.proto", "ped_cycle_pointpillars_xyres_24_near_0_5_pure", "full-subscene"],
        ["./configs/pointpillars/ped_cycle/xyres_28.proto", "ped_cycle_pointpillars_xyres_28_near_0_5_pure", "full-subscene"],
        ["./configs/pointpillars/ped_cycle/xyres_32.proto", "ped_cycle_pointpillars_xyres_32_near_0_5_pure", "full-subscene"],
        ["./configs/pointpillars/ped_cycle/xyres_48.proto", "ped_cycle_pointpillars_xyres_48_near_0_5_pure", "full-subscene"],
        ["./configs/pointpillars/ped_cycle/xyres_56.proto", "ped_cycle_pointpillars_xyres_56_near_0_5_pure", "full-subscene"],

        ["./configs/pointpillars/car/near_far/xyres_16_near_0.5.proto", "car_pointpillars_xyres_16_pure", "near-0.5"],
        ["./configs/pointpillars/car/near_far/xyres_20_near_0.5.proto", "car_pointpillars_xyres_20_pure", "near-0.5"],
        ["./configs/pointpillars/car/near_far/xyres_24_near_0.5.proto", "car_pointpillars_xyres_24_pure", "near-0.5"],
        ["./configs/pointpillars/car/near_far/xyres_28_near_0.5.proto", "car_pointpillars_xyres_28_pure", "near-0.5"],

        ["./configs/pointpillars/car/xyres_16.proto", "car_pointpillars_xyres_16_near_0_5_pure", "full-subscene"],
        ["./configs/pointpillars/car/xyres_20.proto", "car_pointpillars_xyres_20_near_0_5_pure", "full-subscene"],
        ["./configs/pointpillars/car/xyres_24.proto", "car_pointpillars_xyres_24_near_0_5_pure", "full-subscene"],
        ["./configs/pointpillars/car/xyres_28.proto", "car_pointpillars_xyres_28_near_0_5_pure", "full-subscene"],


        ["./configs/pointpillars/ped_cycle/xyres_16.proto", "ped_cycle_pointpillars_xyres_16_pure", "full-subscene"],
        ["./configs/pointpillars/ped_cycle/xyres_16.proto", "ped_cycle_pointpillars_xyres_16_pure_2", "full-subscene"],
        ["./configs/pointpillars/ped_cycle/xyres_16.proto", "ped_cycle_pointpillars_xyres_16_pure_3", "full-subscene"],
        ["./configs/pointpillars/ped_cycle/xyres_20.proto", "ped_cycle_pointpillars_xyres_20_pure", "full-subscene"],
        ["./configs/pointpillars/ped_cycle/xyres_24.proto", "ped_cycle_pointpillars_xyres_24_pure", "full-subscene"],
        ["./configs/pointpillars/ped_cycle/xyres_28.proto", "ped_cycle_pointpillars_xyres_28_pure", "full-subscene"],
        ["./configs/pointpillars/ped_cycle/xyres_32.proto", "ped_cycle_pointpillars_xyres_32_pure", "full-subscene"],
        ["./configs/pointpillars/ped_cycle/xyres_48.proto", "ped_cycle_pointpillars_xyres_48_pure", "full-subscene"],
        ["./configs/pointpillars/ped_cycle/xyres_56.proto", "ped_cycle_pointpillars_xyres_56_pure", "full-subscene"],
        
        ["./configs/pointpillars/ped_cycle/near_far/xyres_16_near_0.5.proto", "ped_cycle_pointpillars_xyres_16_near_0_5_pure", "near-0.5"],
        ["./configs/pointpillars/ped_cycle/near_far/xyres_20_near_0.5.proto", "ped_cycle_pointpillars_xyres_20_near_0_5_pure", "near-0.5"],
        ["./configs/pointpillars/ped_cycle/near_far/xyres_24_near_0.5.proto", "ped_cycle_pointpillars_xyres_24_near_0_5_pure", "near-0.5"],
        ["./configs/pointpillars/ped_cycle/near_far/xyres_28_near_0.5.proto", "ped_cycle_pointpillars_xyres_28_near_0_5_pure", "near-0.5"],
        ["./configs/pointpillars/ped_cycle/near_far/xyres_32_near_0.5.proto", "ped_cycle_pointpillars_xyres_32_near_0_5_pure", "near-0.5"],
        ["./configs/pointpillars/ped_cycle/near_far/xyres_48_near_0.5.proto", "ped_cycle_pointpillars_xyres_48_near_0_5_pure", "near-0.5"],
        ["./configs/pointpillars/ped_cycle/near_far/xyres_56_near_0.5.proto", "ped_cycle_pointpillars_xyres_56_near_0_5_pure", "near-0.5"],

        ["./configs/pointpillars/car/xyres_16.proto", "car_pointpillars_xyres_16_pure", "full-subscene"],
        ["./configs/pointpillars/car/xyres_20.proto", "car_pointpillars_xyres_20_pure", "full-subscene"],
        ["./configs/pointpillars/car/xyres_24.proto", "car_pointpillars_xyres_24_pure", "full-subscene"],
        ["./configs/pointpillars/car/xyres_28.proto", "car_pointpillars_xyres_28_pure", "full-subscene"],

        ["./configs/pointpillars/car/near_far/xyres_16_near_0.5.proto", "car_pointpillars_xyres_16_near_0_5_pure", "near-0.5"],
        ["./configs/pointpillars/car/near_far/xyres_20_near_0.5.proto", "car_pointpillars_xyres_20_near_0_5_pure", "near-0.5"],
        ["./configs/pointpillars/car/near_far/xyres_24_near_0.5.proto", "car_pointpillars_xyres_24_near_0_5_pure", "near-0.5"],
        ["./configs/pointpillars/car/near_far/xyres_28_near_0.5.proto", "car_pointpillars_xyres_28_near_0_5_pure", "near-0.5"],


    ];

    evaluationModes = [

        "1/2",
        "1/1",
    ];

    
    const allParams = [
        ...combine(configPaths, evaluationModes),
    ];

    allParams.forEach(([[configPath, configName, metricsName], evaluationMode]) => {

        const totalName = [configName].join('_');

        const configPathValue = `--config_path=${configPath}`;
        const modelDirValue = `--model_dir=/home/io3/TANet/pointpillars_with_TANet/models-pointpillars/${totalName}`;
        // const pointpillarsConfigValue = `--pointpillars_config=./configs/pointpillars/pointpillars.yaml`;
        // const refineWeightValue = `--refine_weight=${refineWeight}`;
        // const gradLimitValue = `--grad_limit=10`;
        const metricsNameValue = `--metrics_file_name=${metricsName}-metrics.txt`;
        const evaluationModeValue = `--evaluation_mode=${evaluationMode}`;

        const totalValues = [
            configPathValue, modelDirValue,
            // pointpillarsConfigValue, refineWeightValue, gradLimitValue,
            configPathValue, metricsNameValue, evaluationModeValue
        ].join(' ');
        
        toAdd.push([
            workstatons, 1, 10000, 'pointpillars_' + totalName + `_eval_${evaluationMode.replace('/', '_')}`, `scripts/run.sh evaluate ${totalValues}`,
            '~/TANet/pointpillars_with_TANet/second', false
        ]);
    });

    console.log('toAdd: ', toAdd.map(a => a[0] + '::' + a[3]));
};


var apply = (randomize = false) => {

    let added = 0;
    let total = toAdd.length;

    const addTask = (
        randomize
        ? (t) => setTimeout(() => { add(...t); added ++; console.log(`[${added}/${total}]`); }, Math.random() * 1000)
        : (t) => { add(...t); added ++; console.log(`[${added}/${total}]`); }
    );

    toAdd.forEach(addTask);
    toAdd = [];
};

createTasks('cerberus');
apply();