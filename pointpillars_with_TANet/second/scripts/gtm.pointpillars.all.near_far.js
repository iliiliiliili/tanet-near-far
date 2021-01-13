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
        
        ["./configs/pointpillars/ped_cycle/xyres_16.proto", "ped_cycle_pointpillars_xyres_16_pure", 5],
        ["./configs/pointpillars/ped_cycle/xyres_16.proto", "ped_cycle_pointpillars_xyres_16_pure_2", 5],
        ["./configs/pointpillars/ped_cycle/xyres_16.proto", "ped_cycle_pointpillars_xyres_16_pure_3", 5],
        ["./configs/pointpillars/ped_cycle/xyres_20.proto", "ped_cycle_pointpillars_xyres_20_pure", 5],
        ["./configs/pointpillars/ped_cycle/xyres_24.proto", "ped_cycle_pointpillars_xyres_24_pure", 5],
        ["./configs/pointpillars/ped_cycle/xyres_28.proto", "ped_cycle_pointpillars_xyres_28_pure", 5],
        ["./configs/pointpillars/ped_cycle/xyres_32.proto", "ped_cycle_pointpillars_xyres_32_pure", 5],
        ["./configs/pointpillars/ped_cycle/xyres_48.proto", "ped_cycle_pointpillars_xyres_48_pure", 5],
        ["./configs/pointpillars/ped_cycle/xyres_56.proto", "ped_cycle_pointpillars_xyres_56_pure", 5],
        
        ["./configs/pointpillars/ped_cycle/near_far/xyres_16_near_0.5.proto", "ped_cycle_pointpillars_xyres_16_near_0_5_pure", 5],
        ["./configs/pointpillars/ped_cycle/near_far/xyres_20_near_0.5.proto", "ped_cycle_pointpillars_xyres_20_near_0_5_pure", 5],
        ["./configs/pointpillars/ped_cycle/near_far/xyres_24_near_0.5.proto", "ped_cycle_pointpillars_xyres_24_near_0_5_pure", 5],
        ["./configs/pointpillars/ped_cycle/near_far/xyres_28_near_0.5.proto", "ped_cycle_pointpillars_xyres_28_near_0_5_pure", 5],
        ["./configs/pointpillars/ped_cycle/near_far/xyres_32_near_0.5.proto", "ped_cycle_pointpillars_xyres_32_near_0_5_pure", 5],
        ["./configs/pointpillars/ped_cycle/near_far/xyres_48_near_0.5.proto", "ped_cycle_pointpillars_xyres_48_near_0_5_pure", 5],
        ["./configs/pointpillars/ped_cycle/near_far/xyres_56_near_0.5.proto", "ped_cycle_pointpillars_xyres_56_near_0_5_pure", 5],

        ["./configs/pointpillars/car/xyres_16.proto", "car_pointpillars_xyres_16_pure", 2],
        ["./configs/pointpillars/car/xyres_20.proto", "car_pointpillars_xyres_20_pure", 2],
        ["./configs/pointpillars/car/xyres_24.proto", "car_pointpillars_xyres_24_pure", 2],
        ["./configs/pointpillars/car/xyres_28.proto", "car_pointpillars_xyres_28_pure", 2],

        ["./configs/pointpillars/car/near_far/xyres_16_near_0.5.proto", "car_pointpillars_xyres_16_near_0_5_pure", 2],
        ["./configs/pointpillars/car/near_far/xyres_20_near_0.5.proto", "car_pointpillars_xyres_20_near_0_5_pure", 2],
        ["./configs/pointpillars/car/near_far/xyres_24_near_0.5.proto", "car_pointpillars_xyres_24_near_0_5_pure", 2],
        ["./configs/pointpillars/car/near_far/xyres_28_near_0.5.proto", "car_pointpillars_xyres_28_near_0_5_pure", 2],
    ];

    
    const allParams = [
        ...combine(configPaths),
    ];

    allParams.forEach(([[configPath, configName, refineWeight]]) => {

        const totalName = [configName].join('_');

        const configPathValue = `--config_path=${configPath}`;
        const modelDirValue = `--model_dir=/home/io3/TANet/pointpillars_with_TANet/models-pointpillars/${totalName}`;
        const refineWeightValue = `--refine_weight=${refineWeight}`;
        const gradLimitValue = `--grad_limit=10`;

        const totalValues = [
            configPathValue, modelDirValue,
            refineWeightValue, gradLimitValue,
            configPathValue,
        ].join(' ');
        
        toAdd.push([
            workstatons, 1, 10000, 'pointpillars_' + totalName, `scripts/run.sh train ${totalValues}`,
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