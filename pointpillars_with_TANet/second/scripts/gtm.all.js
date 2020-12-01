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

        ["./configs/tanet/ped_cycle/xyres_16.proto", "ped_cycle_tanet_xyres_16"],
        ["./configs/tanet/ped_cycle/xyres_20.proto", "ped_cycle_tanet_xyres_20"],
        ["./configs/tanet/ped_cycle/xyres_24.proto", "ped_cycle_tanet_xyres_24"],
        ["./configs/tanet/ped_cycle/xyres_28.proto", "ped_cycle_tanet_xyres_28"],
        ["./configs/tanet/ped_cycle/xyres_32.proto", "ped_cycle_tanet_xyres_32"],
        ["./configs/tanet/ped_cycle/xyres_48.proto", "ped_cycle_tanet_xyres_48"],
        ["./configs/tanet/ped_cycle/xyres_56.proto", "ped_cycle_tanet_xyres_56"],
    ];

    
    const allParams = [
        ...combine(configPaths),
    ];

    allParams.forEach(([[configPath, configName]]) => {

        const psaName = `tanet`;

        const totalName = ["ped_cycle", psaName, configName].join('_');

        const configPathValue = `--config_path=${configPath}`;
        const modelDirValue = `--model_dir=/home/io/Detection/Models/tanet/TANet/pointpillars_with_TANet/${totalName}`;
        const tanetConfigValue = `--tanet_config=./configs/tanet/tanet.yaml`;
        const refineWeightValue = `--refine_weight=5`;
        const gradLimitValue = `--grad_limit=10`;

        const totalValues = [
            configPathValue, modelDirValue, tanetConfigValue,
            refineWeightValue, gradLimitValue,
            configPathValue,
        ].join(' ');
        
        toAdd.push([
            workstatons, 1, 10000, 'tanet_' + totalName, `scripts/run.sh train ${totalValues}`,
            '~/Detection/Models/tanet/TANet/pointpillars_with_TANet/second', false
        ]);
    });

    console.log('toAdd: ', toAdd.map(a => a[0] + '::' + a[3]));
};


var apply = (randomize = true) => {

    let added = 0;
    let total = toAdd.length;

    const addTask = (
        randomize
        ? (t) => { add(...t); added ++; console.log(`[${added}/${total}]`); }
        : (t) => setTimeout(() => { add(...t); added ++; console.log(`[${added}/${total}]`); }, Math.random() * 1000)
    );

    toAdd.forEach(addTask);
    toAdd = [];
};

createTasks('cerberus');
apply();