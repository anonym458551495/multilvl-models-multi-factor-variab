import numpyro
from analysis import Analysis
import matplotlib

# must be run before any JAX imports
numpyro.set_host_device_count(50)

import argparse
from experiment import (
    Replication,
    ExperimentTransfer,
    ExperimentMultitask,
    MLFLOW_URI,
    EXPERIMENT_NAME,
)
import os
import localflow as mlflow
from data import (
    DataLoaderStandard,
    DataAdapterJump3r,
    WorkloadTrainingDataSet,
    DataAdapterXZ,
    DataLoaderDashboardData,
    DataAdapterH2,
    Standardizer,
    PaiwiseOptionMapper,
    DataAdapterX264,
    DataAdapterBatik,
    DataAdapterDConvert,
    DataAdapterKanzi,
    DataAdapterZ3,
    DataAdapterLrzip,
    DataAdapterFastdownward,
    DataAdapterArtificial,
    DataAdapterVP9,
)
from sklearn.ensemble import RandomForestRegressor
from sklearn.linear_model import LinearRegression, Lasso
from sklearn.dummy import DummyRegressor
from models import (
    MCMCMultilevelPartial,
    NoPoolingEnvModel,
    CompletePoolingEnvModel,
    MCMCCombinedNoPooling,
    MCMCPartialRobustLasso,
    MCMCPartialHorseshoe,
    MCMCCombinedCompletePooling,
    MCMCPartialSelfStandardizing,
    MCMCPartialRobustLassoAdaptiveShrinkage,
    MCMCPartialSelfStandardizingConstInfl,
    MCMCRHS,LassoGridSearchCV
)
import mlfloweval


def get_rep_ids(default_n_reps, custom_num_reps=None, rep_offset=0):
    if custom_num_reps:
        print("custom num_reps:", custom_num_reps)
        print("custom rep_offset:", rep_offset)
        rep_ids = list(range(rep_offset, custom_num_reps + rep_offset))
    else:
        rep_ids = list(range(default_n_reps))
    print(f"Generated repetidion random seeds:", rep_ids)
    return rep_ids


def main():
    mlflow.set_tracking_uri(MLFLOW_URI)
    parser = argparse.ArgumentParser(description="Script description")
    parser.add_argument(
        "--jobs", type=int, default=None, help="Number of jobs for parallel mode"
    )
    parser.add_argument(
        "--reps", type=int, default=None, help="Number of repetitions for experiment"
    )
    parser.add_argument(
        "--rep-offset",
        type=int,
        default=0,
        help="Offsets for the random number generation",
    )
    parser.add_argument("--debug", action="store_true", help="Enable debug mode")
    parser.add_argument("--plot", action="store_true", help="Enable debug mode")
    parser.add_argument("--store", action="store_true", help="Enable debug mode")
    # parser.add_argument(
    #     "--experiments",
    #     default=experiment_class_labels.keys(),
    #     choices=experiment_class_labels.keys(),
    #     nargs="*",
    #     help="allows selecting individual experiments",
    # )
    parser.add_argument('--training-set-size', type=float,
                        help="Disables the sweep over different training set sizes and uses the given size")
    args = parser.parse_args()
    n_jobs = args.jobs
    debug = args.debug
    plot = args.plot
    do_store = args.store
    num_reps = args.reps
    rep_offset = args.rep_offset
    training_set_size = args.training_set_size
    chosen_experiments = [ExperimentMultitask]
    print("Preparing experiments", chosen_experiments)

    print("pwd", os.getcwd())
    print("Storing arviz data?", do_store)
    models = get_all_models(debug, n_jobs, plot, do_store=do_store)

    rep_lbl = "full-run"
    if debug:
        pass
    else:
        os.environ['TF_CPP_MIN_LOG_LEVEL'] = '2'
        train_sizes = (
            0.125,
            0.25,
            0.5,
            0.75,
            1.0,
            2,
            3,
        )

        default_n_reps = 3
        rnds = get_rep_ids(default_n_reps, num_reps, rep_offset)

        selected_data = (
            "jump3r",
            "xz",
            "x264",
            "lrzip",
            "z3",
            "VP9",
            "x265",
            "batik",
            "dconvert",
            "H2",
        )
        if training_set_size is not None:
            train_sizes = (
                training_set_size,
            )
        chosen_model_lbls = []


        #FINALS
        chosen_model_lbls.extend(["no-pooling-mcmc-1model"])
        chosen_model_lbls.extend(["cpooling-mcmc-1model"])
        chosen_model_lbls.extend(["partial-pooling-mcmc-robust-adaptive-shrinkage"])
        # #
        chosen_model_lbls.extend(["model_lasso_reg_cpool"])
        chosen_model_lbls.extend(["model_lasso_reg_no_pool"])
        chosen_model_lbls.extend(["no-pooling-dummy"])
        chosen_model_lbls.extend(["cpooling-dummy"])

        chosen_model_lbls.extend(["model_lassocv_reg_no_pool"])
        chosen_model_lbls.extend(["model_lassocv_reg_cpool"])


    models = {k: v for k, v in models.items() if k in chosen_model_lbls}

    print("Using systems:", selected_data)
    print("With training set size N=", train_sizes)
    print(f"And rnd seeds", rnds)
    data_providers = get_datasets(dataset_lbls=selected_data)

    print("created models")

    # data_providers = {key: data_providers[key] for key in selected_data}

    rep = Replication(
        chosen_experiments,
        models,
        data_providers,
        train_sizes,
        rnds,
        n_jobs=n_jobs,
        replication_lbl=rep_lbl,
    )
    run_id = rep.run()

    # eval = Evaluation()
    print("DONE with experiment.")
    print("running analysis")
    eval = mlfloweval.Evaluation(run_id, MLFLOW_URI, EXPERIMENT_NAME)
    eval.run()



def get_all_models(debug, n_jobs, plot, do_store=False):
    if debug:
        mcmc_num_warmup = 500
        mcmc_num_samples = 500
        mcmc_num_chains = 3
    else:
        mcmc_num_warmup = 1000
        mcmc_num_samples = 1000
        mcmc_num_chains = 3
    progress_bar = False if n_jobs else True
    mcmc_kwargs = {
        "num_warmup": mcmc_num_warmup,
        "num_samples": mcmc_num_samples,
        "num_chains": mcmc_num_chains,
        "progress_bar": progress_bar,
    }
    rf_proto = RandomForestRegressor()
    model_rf = NoPoolingEnvModel(rf_proto, preprocessings=[Standardizer()])

    complete_pooling_rf = CompletePoolingEnvModel(rf_proto, preprocessings=[Standardizer()])
    lin_reg_proto = LinearRegression()
    model_lin_reg = NoPoolingEnvModel(lin_reg_proto, preprocessings=[Standardizer()])
    model_lin_reg_cpool = CompletePoolingEnvModel(
        lin_reg_proto, preprocessings=[Standardizer()]
    )
    model_lin_reg_cpool_pw = CompletePoolingEnvModel(
        lin_reg_proto, preprocessings=[PaiwiseOptionMapper(), Standardizer()]
    )

    model_lin_reg_pw = NoPoolingEnvModel(
        lin_reg_proto, preprocessings=[PaiwiseOptionMapper(), Standardizer()]
    )

    lasso_proto = Lasso(random_state=0)
    model_lasso_reg_no_pool = NoPoolingEnvModel(
        lasso_proto, preprocessings=[Standardizer()]
    )

    lasso_proto = Lasso(random_state=0)
    model_lasso_reg_cpool = CompletePoolingEnvModel(
        lasso_proto, preprocessings=[Standardizer()]
    )

    lassocv_proto = LassoGridSearchCV()
    model_lassocv_reg_no_pool = NoPoolingEnvModel(
        lassocv_proto, preprocessings=[Standardizer()]
    )

    lasso_proto = Lasso(random_state=0)
    model_lassocv_reg_cpool = CompletePoolingEnvModel(
        lassocv_proto, preprocessings=[Standardizer()]
    )




    # model_lin_reg_poly = Poly
    dummy_proto = DummyRegressor()
    model_dummy = NoPoolingEnvModel(dummy_proto)
    model_dummy_cpool = CompletePoolingEnvModel(dummy_proto)
    model_partial_extra_standardization = MCMCMultilevelPartial(
        plot=plot,
        **mcmc_kwargs,
        return_samples_by_default=True,
        preprocessings=[Standardizer()],
        persist_arviz=do_store,
    )

    model_partial_extra_standardization_pw = MCMCMultilevelPartial(
        plot=plot,
        **mcmc_kwargs,
        return_samples_by_default=True,
        preprocessings=[PaiwiseOptionMapper(), Standardizer()],
        persist_arviz=do_store,
    )

    model_multilevel_partial_robust = MCMCPartialRobustLasso(
        plot=plot,
        **mcmc_kwargs,
        return_samples_by_default=True,
        preprocessings=[Standardizer()],
        persist_arviz=do_store,
    )

    model_multilevel_partial_robust_adaptive_shrinkage = (
        MCMCPartialRobustLassoAdaptiveShrinkage(
            plot=plot,
            **mcmc_kwargs,
            return_samples_by_default=True,
            preprocessings=[Standardizer()],
            persist_arviz=do_store,
        )
    )

    model_multilevel_partial_robust_adaptive_shrinkage_pw = (
        MCMCPartialRobustLassoAdaptiveShrinkage(
            plot=plot,
            **mcmc_kwargs,
            return_samples_by_default=True,
            preprocessings=[PaiwiseOptionMapper(), Standardizer()],
            persist_arviz=do_store,
        )
    )

    model_multilevel_partial_robust_pw = MCMCPartialRobustLasso(
        plot=plot,
        **mcmc_kwargs,
        return_samples_by_default=True,
        preprocessings=[PaiwiseOptionMapper(), Standardizer()],
        persist_arviz=do_store,
    )
    model_no_pooling_combined = MCMCCombinedNoPooling(
        plot=plot,
        **mcmc_kwargs,
        return_samples_by_default=True,
        preprocessings=[Standardizer()],
        persist_arviz=do_store,
    )
    model_no_pooling_combined_pw = MCMCCombinedNoPooling(
        plot=plot,
        **mcmc_kwargs,
        return_samples_by_default=True,
        preprocessings=[PaiwiseOptionMapper(), Standardizer()],
        persist_arviz=do_store,
    )
    model_multilevel_partial_horseshoe = MCMCPartialHorseshoe(
        plot=plot,
        **mcmc_kwargs,
        return_samples_by_default=True,
        preprocessings=[Standardizer()],
        persist_arviz=do_store,
    )
    model_multilevel_partial_RHS = MCMCRHS(
        plot=plot,
        **mcmc_kwargs,
        return_samples_by_default=True,
        preprocessings=[Standardizer()],
        persist_arviz=do_store,
    )
    model_multilevel_partial_RHS_pw = MCMCRHS(
        plot=plot,
        **mcmc_kwargs,
        return_samples_by_default=True,
        preprocessings=[PaiwiseOptionMapper(), Standardizer()],
        persist_arviz=do_store,
    )
    model_multilevel_partial_horseshoe_pw = MCMCPartialHorseshoe(
        plot=plot,
        **mcmc_kwargs,
        return_samples_by_default=True,
        preprocessings=[PaiwiseOptionMapper(), Standardizer()],
        persist_arviz=do_store,
    )
    model_complete_pooling_combined = MCMCCombinedCompletePooling(
        plot=plot,
        **mcmc_kwargs,
        return_samples_by_default=True,
        preprocessings=[Standardizer()],
        persist_arviz=do_store,
    )
    model_complete_pooling_combined_pw = MCMCCombinedCompletePooling(
        plot=plot,
        **mcmc_kwargs,
        return_samples_by_default=True,
        preprocessings=[PaiwiseOptionMapper(), Standardizer()],
        persist_arviz=do_store,
    )
    model_partial_diff = MCMCPartialSelfStandardizing(
        plot=plot,
        **mcmc_kwargs,
        return_samples_by_default=True,
        preprocessings=[
            Standardizer(standardize_y=False),
        ],
        persist_arviz=do_store,
    )
    model_selfstd_const = MCMCPartialSelfStandardizingConstInfl(
        plot=plot,
        **mcmc_kwargs,
        return_samples_by_default=True,
        preprocessings=[
            Standardizer(standardize_y=False),
        ],
        persist_arviz=do_store,
    )

    models = {
        "partial-pooling-mcmc-extra": model_partial_extra_standardization,
        "partial-pooling-mcmc-extra-pw": model_partial_extra_standardization_pw,
        "partial-pooling-mcmc-robust": model_multilevel_partial_robust,
        "partial-pooling-mcmc-robust-adaptive-shrinkage": model_multilevel_partial_robust_adaptive_shrinkage,
        "partial-pooling-mcmc-robust-adaptive-shrinkage-pw": model_multilevel_partial_robust_adaptive_shrinkage_pw,
        "partial-pooling-mcmc-robust-pw": model_multilevel_partial_robust_pw,
        "no-pooling-rf": model_rf,
        "no-pooling-lin-pw": model_lin_reg_pw,
        "no-pooling-lin": model_lin_reg,
        "cpooling-lin": model_lin_reg_cpool,
        "cpooling-lin-pw": model_lin_reg_cpool_pw,
        "no-pooling-dummy": model_dummy,
        "cpooling-dummy": model_dummy_cpool,
        "cpooling-rf": complete_pooling_rf,
        "no-pooling-mcmc-1model": model_no_pooling_combined,
        "no-pooling-mcmc-1model-pw": model_no_pooling_combined_pw,
        "cpooling-mcmc-1model": model_complete_pooling_combined,
        "cpooling-mcmc-1model-pw": model_complete_pooling_combined_pw,
        "partial-pooling-mcmc-horseshoe": model_multilevel_partial_horseshoe,
        "partial-pooling-mcmc-horseshoe-pw": model_multilevel_partial_horseshoe_pw,
        "partial-pooling-mcmc-selfstd": model_partial_diff,
        "mcmc-selfstd-const-hyper": model_selfstd_const,
        "partial-pooling-mcmc-RHS": model_multilevel_partial_RHS,
        "partial-pooling-mcmc-RHS-pw": model_multilevel_partial_RHS_pw,
        "model_lasso_reg_cpool": model_lasso_reg_cpool,
        "model_lasso_reg_no_pool": model_lasso_reg_no_pool,
        "model_lassocv_reg_no_pool": model_lassocv_reg_no_pool,
        "model_lassocv_reg_cpool": model_lassocv_reg_cpool,
    }
    return models


def get_datasets(train_data_folder=None, dataset_lbls=None):
    lbl_jump_r = "jump3r"
    lbl_H2 = "H2"
    lbl_xz = "xz"
    lbl_x264 = "x264"
    lbl_x265 = "x265"
    lbl_batik = "batik"
    lbl_dconvert = "dconvert"
    lbl_kanzi = "kanzi"
    lbl_lrzip = "lrzip"
    lbl_z3 = "z3"
    lbl_fastdownward = "fastdownward"
    lbl_artificial = "artificial"
    lbl_VP9 = "VP9"
    all_lbls = [
        lbl_jump_r,
        lbl_H2,
        lbl_xz,
        lbl_x264,
        lbl_x265,
        lbl_batik,
        lbl_dconvert,
        lbl_kanzi,
        lbl_lrzip,
        lbl_z3,
        lbl_fastdownward,
        lbl_artificial,
        lbl_VP9,
    ]
    dataset_lbls = dataset_lbls or all_lbls

    data_providers = {}

    print("loading data")
    train_data_folder = train_data_folder or "./training-data"
    if lbl_H2 in dataset_lbls:
        path_h2 = os.path.join(train_data_folder, "dashboard-resources/h2/")
        h2_data_raw = DataLoaderDashboardData(path_h2)
        data_H2 = DataAdapterH2(h2_data_raw)
        h2_wl_data: WorkloadTrainingDataSet = data_H2.get_wl_data()
        data_providers[lbl_H2] = h2_wl_data

    if lbl_xz in dataset_lbls:
        path_xz = os.path.join(train_data_folder, "dashboard-resources/xz/")
        xz_data_raw = DataLoaderDashboardData(path_xz)
        data_xz = DataAdapterXZ(xz_data_raw)
        xz_wl_data: WorkloadTrainingDataSet = data_xz.get_wl_data()
        data_providers[lbl_xz] = xz_wl_data

    if lbl_jump_r in dataset_lbls:
        path_jump3r = os.path.join(train_data_folder, "jump3r.csv")
        jump3r_data_raw = DataLoaderStandard(path_jump3r)
        data_jump3r = DataAdapterJump3r(jump3r_data_raw)
        wl_data_jump3r: WorkloadTrainingDataSet = data_jump3r.get_wl_data()
        data_providers[lbl_jump_r] = wl_data_jump3r

    if lbl_x264 in dataset_lbls:
        path_x264 = os.path.join(train_data_folder, "dashboard-resources/x264/")
        x264_data_raw = DataLoaderDashboardData(path_x264)
        data_x264 = DataAdapterX264(x264_data_raw)
        x264_wl_data: WorkloadTrainingDataSet = data_x264.get_wl_data()
        data_providers[lbl_x264] = x264_wl_data

    if lbl_batik in dataset_lbls:
        path_batik = os.path.join(train_data_folder, "dashboard-resources/batik/")
        batik_data_raw = DataLoaderDashboardData(path_batik)
        data_batik = DataAdapterBatik(batik_data_raw)
        batik_wl_data: WorkloadTrainingDataSet = data_batik.get_wl_data()
        data_providers[lbl_batik] = batik_wl_data

    if lbl_dconvert in dataset_lbls:
        path_dconvert = os.path.join(train_data_folder, "dashboard-resources/dconvert/")
        dconvert_data_raw = DataLoaderDashboardData(path_dconvert)
        data_dconvert = DataAdapterDConvert(dconvert_data_raw)
        dconvert_wl_data: WorkloadTrainingDataSet = data_dconvert.get_wl_data()
        data_providers[lbl_dconvert] = dconvert_wl_data

    if lbl_kanzi in dataset_lbls:
        path_kanzi = os.path.join(train_data_folder, "dashboard-resources/kanzi/")
        kanzi_data_raw = DataLoaderDashboardData(path_kanzi)
        data_kanzi = DataAdapterKanzi(kanzi_data_raw)
        kanzi_wl_data: WorkloadTrainingDataSet = data_kanzi.get_wl_data()
        data_providers[lbl_kanzi] = kanzi_wl_data

    if lbl_lrzip in dataset_lbls:
        path_lrzip = os.path.join(train_data_folder, "dashboard-resources/lrzip/")
        lrzip_data_raw = DataLoaderDashboardData(path_lrzip)
        data_lrzip = DataAdapterLrzip(lrzip_data_raw)
        lrzip_wl_data: WorkloadTrainingDataSet = data_lrzip.get_wl_data()
        data_providers[lbl_lrzip] = lrzip_wl_data

    if lbl_z3 in dataset_lbls:
        path_z3 = os.path.join(train_data_folder, "dashboard-resources/z3/")
        z3_data_raw = DataLoaderDashboardData(path_z3)
        data_z3 = DataAdapterZ3(z3_data_raw)
        z3_wl_data: WorkloadTrainingDataSet = data_z3.get_wl_data()
        data_providers[lbl_z3] = z3_wl_data

    if lbl_fastdownward in dataset_lbls:
        path_fastdownward = os.path.join(
            train_data_folder, "FastDownward_Data/measurements.csv"
        )
        fastdownward_data_raw = DataLoaderStandard(path_fastdownward)
        data_fastdownward = DataAdapterFastdownward(fastdownward_data_raw)
        fastdownward_wl_data: WorkloadTrainingDataSet = data_fastdownward.get_wl_data()
        data_providers[lbl_fastdownward] = fastdownward_wl_data

    if lbl_artificial in dataset_lbls:
        path_artificial = os.path.join(
            train_data_folder, "artificial/artificial_data.csv"
        )
        artificial_data_raw = DataLoaderStandard(path_artificial)
        data_artificial = DataAdapterArtificial(artificial_data_raw, noise_std=1.0)
        artificial_wl_data: WorkloadTrainingDataSet = data_artificial.get_wl_data()
        data_providers[lbl_artificial] = artificial_wl_data

    if lbl_VP9 in dataset_lbls:
        path_vp9 = os.path.join(
            train_data_folder,
            "performance-across-workloads-and-evolution/vp9/measurements_1.13.0-t_wise.csv",
        )
        vp9_data_raw = DataLoaderStandard(path_vp9)
        data_vp9 = DataAdapterVP9(vp9_data_raw)
        vp9_wl_data: WorkloadTrainingDataSet = data_vp9.get_wl_data()
        data_providers[lbl_VP9] = vp9_wl_data

    if lbl_x265 in dataset_lbls:
        path_x265 = os.path.join(
            train_data_folder,
            "performance-across-workloads-and-evolution/x265/measurements_3.5-t_wise.csv",
        )
        x265_data_raw = DataLoaderStandard(path_x265)
        data_x265 = DataAdapterVP9(x265_data_raw)
        x265_wl_data: WorkloadTrainingDataSet = data_x265.get_wl_data()
        data_providers[lbl_x265] = x265_wl_data

    print("loaded data")
    return data_providers


if __name__ == "__main__":
    main()
