import argparse
import subprocess
import os
import time

port1 = 8083
port2 = 8084

cwd_wluncert = '/app/wluncert'


def main():
    parser = argparse.ArgumentParser(description="Entrypoint for Docker container tasks")

    parser.add_argument('command', choices=["rq1", "rq23", 'custom-experiment'], help="The command to run")
    parser.add_argument('--jobs', type=int, default=1, help="Defines how many models are trained in parallel")
    parser.add_argument('--store', action='store_true', help="Store insights into posterior distributions")
    parser.add_argument('--reps', type=int, default=None, help="Defines the number of repetitions")
    parser.add_argument('--training-set-size', type=float,
                        help="Disables the sweep over different training set sizes and uses the given size")

    args = parser.parse_args()

    os.chdir(cwd_wluncert)
    jobs = args.jobs
    store = args.store
    training_set_size = args.training_set_size
    reps = args.reps

    if args.command == 'custom-experiment':
        run_experiment(jobs, reps, store, training_set_size)
        run_metrics_dashboard(blocking=False)
        run_insights_dashboard()
    elif args.command == 'rq1':
        run_RQ1(jobs=jobs, reps=reps, training_set_size=training_set_size)
    elif args.command == 'rq23':
        run_RQ2_and_RQ3(jobs=jobs, training_set_size=training_set_size)

    else:
        print(f"Unknown command: {args.command}")


def start_dashboards():
    run_metrics_dashboard()
    time.sleep(0.25)
    run_insights_dashboard()


def run_RQ1(jobs, reps, training_set_size):
    store = False
    reps = reps or 30
    run_experiment(jobs, reps, store, training_set_size)
    run_metrics_dashboard()


def run_RQ2_and_RQ3(jobs, training_set_size=None):
    store = True
    training_set_size = training_set_size or 3.0
    run_experiment(jobs, 1, store, training_set_size)
    run_insights_dashboard()


def run_metrics_dashboard(blocking=True):
    cmd = ["streamlit", "run", "playground/metricsdashboard.py", "--server.port", str(port1),
           "browser.gatherUsageStats", "False"]
    run(cmd, blocking)


def run_insights_dashboard(blocking=True):
    cmd = ["streamlit", "run", "playground/insights-dashboard.py", "--server.port", str(port2),
           "browser.gatherUsageStats", "False"]
    run(cmd, blocking)


def run(cmd, blocking=True):
    blocking_str = "BLOCKING" if blocking else "[ASYNC]"
    print(f"[{blocking_str}] {str(blocking_str)}")
    if blocking:
        subprocess.run(cmd, cwd=cwd_wluncert)
    else:
        subprocess.Popen(cmd, cwd=cwd_wluncert)


def run_experiment(jobs=1, reps=1, store=False, training_set_size=None):
    # Construct the command for the experiment task
    cmd = ["python3.9", "main.py", "--jobs", str(jobs), "--reps", str(reps)]
    if store:
        cmd.append("--store")
    if training_set_size is not None:
        cmd.extend(["--training-set-size", str(training_set_size)])
    print("Running experiment task with the following command:")
    print(" ".join(cmd))
    # Run the constructed command
    run(cmd)
    insights_cmd = ["python3.9", "modelinsights.py"]
    run(insights_cmd)


if __name__ == "__main__":
    main()
