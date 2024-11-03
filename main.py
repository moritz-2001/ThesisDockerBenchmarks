#!/usr/bin/env python3

import subprocess
import os
import re
import json

def run_command(command):
    res = subprocess.run(command, shell=True, capture_output=True, text=True)
    if res.returncode != 0:
        print(res.stdout)
        print("RETURN CODE: " + str(res.returncode))
        assert False
    return res


def run_commands(commands):
    for command in commands:
        run_command(command)


def gitclone(url, dir_name, target_branch):
    if not os.path.isdir(dir_name):
        run_commands([f"git clone {url} {dir_name}", f"cd {dir_name}; git checkout {target_branch}",
                      f"cd {dir_name}; git submodule update --init --recursive"])
    else:
        old_work_dir = os.getcwd()
        if os.path.isdir("build"):
            assert os.rmdir("build")
        run_command(
            f"cd {dir_name}; git stash; git checkout {target_branch}; git pull; git submodule update --init --recursive")
        os.chdir(old_work_dir)


def build(path, cmake_command, soft_rebuild=False, rebuild=False, install=False):
    old_work_dir = os.getcwd()
    os.chdir(path)

    if os.path.isdir("build") and soft_rebuild:
        os.chdir("build")
        run_command(cmake_command)
        run_command("ninja clean")
        run_command("ninja")
        os.chdir(old_work_dir)
        os.chdir(path)

    if rebuild:
        run_command("rm -rf build")

    if not os.path.isdir("build"):
        os.mkdir("build")
        os.chdir("build")
        run_command(cmake_command)
        run_command("ninja")

    if install:
        os.chdir(old_work_dir)
        os.chdir(path)
        if not os.path.isdir("build"):
            os.mkdir("build")
            os.chdir("build")
            run_command(cmake_command)
        else:
            os.chdir("build")
        run_command("ninja install")

    os.chdir(old_work_dir)


def add_result(name, variant, compilerPass, sgSize, dataType, time, min, throughput=""):
    return [{"name": name, "Variant": variant, "compilerPass": compilerPass, "SG-Size": sgSize, "data-type": dataType,
             "time": time, "min": min, "throughput": throughput}]


def buildAll(compilerOption, rebuild, sgSize, syclBench=True, buildPortblas=True, buildEthMiner=False):
    smcpON = "true" if compilerOption == "rv" or compilerOption == "omp" else "false"
    build("AdaptiveCpp",
          f"cmake -DCMAKE_BUILD_TYPE=Debug -G Ninja -DCMAKE_C_COMPILER=`which clang` -DCMAKE_CXX_COMPILER=`which clang++` -DWITH_SSCP_COMPILER=True  -S .. -DHIPSYCL_DEBUG_LEVEL=0 -DCMAKE_INSTALL_PREFIX=../../install",
          False, rebuild=rebuild, install=True)
    if buildPortblas:
        build("portblas",
              f"cmake -GNinja ../ -DCMAKE_BUILD_TYPE=Release -DSYCL_COMPILER=adaptivecpp -DACPP_TARGETS={compilerOption}",
              True)
    if syclBench:
        build("sycl-bench", f"cmake -G Ninja -S .. -DACPP_TARGETS={compilerOption} -DSMCP={smcpON}", True)
    assert isinstance(sgSize, int)
    if buildEthMiner:
        build("velocity/ethminer",
              f"cmake -DCMAKE_BUILD_TYPE=Release -G Ninja -DCMAKE_C_COMPILER=`which clang` -DCMAKE_CXX_COMPILER=`which clang++` .. -DACPP_TARGETS={compilerOption} -DUSE_SG_SIZE_64={sgSize == 64}",
              True)


def execute(res, func):
        func([])
        func(res)


def benchmarks(compilerOption, variant, sgSize, namePostfix=""):
    res = []

    if sgSize == 32 or sgSize == 64:
        execute(res, lambda res: runEthMiner(res))

    if sgSize > 1:
        execute(res, lambda res: runSyclBench(res, "sg-shuffle"))
        execute(res, lambda res: runSyclBench(res, "sg-shift_left"))
        execute(res, lambda res: runSyclBench(res, "sg-inclusive_scan"))

        execute(res, lambda res: runSyclBench(res, "sg-reduce"))
        execute(res, lambda res: runSyclBench(res, "sg-vote_all"))

    execute(res, lambda res: runSyclBench(res, "group_reduce"))
    execute(res, lambda res: runSyclBench(res, "vote_all"))
    execute(res, lambda res: runSyclBench(res, "group_inclusive_scan"))
    if sgSize <= 32:
        execute(res, lambda res: runSyclBench(res, "matrix_multiply"))

    execute(res, lambda res: runSyclBench(res, "group_reduce_upstream"))
    execute(res, lambda res: runSyclBench(res, "group_inclusive_scan_upstream"))

    execute(res, lambda res: runPortBlas(res, "iamax"))
    execute(res, lambda res: runPortBlas(res, "ger"))

    return [add_result(x["name"] + namePostfix, variant, "SSCP" if compilerOption == "generic" else "SMCP", sgSize,
                       x["data-type"], x["time"], x["min"], x["throughput"]) for x in res]


def benchmarksWithoutReduceIntrinsic(compilerOption, variant):
    res = []

    execute(res, lambda res: runSyclBench(res, "group_reduce"))
    execute(res, lambda res: runSyclBench(res, "vote_all"))
    execute(res, lambda res: runSyclBench(res, "sg-reduce"))
    execute(res, lambda res: runSyclBench(res, "sg-vote_all"))

    return [
        add_result(x["name"] + "-without-reduce-intrinsic", variant, "SSCP" if compilerOption == "generic" else "SMCP",
                   32, x["data-type"], x["time"], x["min"]) for x in res]


def runSyclBench(results, benchmark):
    print(f"RUN SYCL-BENCH: {benchmark}")
    oldWorkDir = os.getcwd()
    os.chdir("sycl-bench/build")

    output = run_command(f"./{benchmark}")

    for bench in output.stdout.split("********** Results for ")[1:]:
        regexRuntime = r"^run-time-median: (.*) \[s\]$"
        regexType = r"^(.*)_.*$"
        mRuntime = re.search(regexRuntime, bench, re.MULTILINE)
        mType = re.search(regexType, bench, re.MULTILINE)
        mMin = re.search(r"^run-time-min: (.*) \[s\]$", bench, re.MULTILINE)
        results += add_result(f"{benchmark}", "", "", 0, mType.group(1), mRuntime.group(1), mMin.group(1))

    regex = r"^Verification: PASS$"
    matches = re.finditer(regex, output.stdout, re.MULTILINE)
    if not sum(1 for _ in matches) == len(output.stdout.split("********** Results for ")[1:]):
        print(output.stdout)
        assert False

    os.chdir(oldWorkDir)


def runPortBlas(results, benchmark):
    print(f"RUN PORTBLAS: {benchmark}")
    oldWorkDir = os.getcwd()
    os.chdir("portblas/build")

    output = run_command(f"./benchmark/portblas/bench_{benchmark} --benchmark_repetitions=10")

    regex = r"^.*<float>\/(.*?)\/.*\/real_time_median.* (.*) ns .* ns .*$"
    matches = re.finditer(regex, output.stdout, re.MULTILINE)

    for matchNum, match in enumerate(matches, start=1):
        results += add_result(f"portblas-{benchmark}-{match.group(1)}", "", "", 0, "", match.group(2), match.group(2))

    os.chdir(oldWorkDir)


def runEthMiner(results):
    oldWorkDir = os.getcwd()
    os.chdir("velocity/ethminer/build")

    output = run_command(f"./ethminer/ethminer -Z 1 --timeout 1000")

    regex = r"^.*Max ([0-9\.]*) Mh Mean.*$"
    matches = re.finditer(regex, output.stderr, re.MULTILINE)

    match = [match for match in matches]
    if len(match) == 0:
        regex = r"^.*Max ([0-9\.]*) Kh Mean.*$"
        matches = re.finditer(regex, output.stderr, re.MULTILINE)
        match = [match for match in matches]
        res = str(float(match[0].group(1)))
        results += add_result(f"ethminer", "", "", 0, "", "", "", res)
    else:
        res = str(float(match[0].group(1)) * 1000)
        results += add_result(f"ethminer", "", "", 0, "", "", "", res)

    os.chdir(oldWorkDir)


def change_sg_size(size):
    oldWorkDir = os.getcwd()
    os.chdir("AdaptiveCpp")
    run_command(
        f"sed -i -E 's/static constexpr size_t SGSize = ([0-9]*);/static constexpr size_t SGSize = {size};/g' include/hipSYCL/compiler/cbs/IRUtils.hpp")
    run_command(
        f"sed -i -E 's/constexpr size_t SGSize = ([0-9]*);/constexpr size_t SGSize = {size};/g' include/hipSYCL/sycl/libkernel/sub_group.hpp ")
    os.chdir(oldWorkDir)


def setUseReduceIntrinsic(cond):
    oldWorkDir = os.getcwd()
    os.chdir("AdaptiveCpp/include/hipSYCL")
    string = "true" if cond else "false"
    assert subprocess.run(
        f"sed -i -E 's/#define USE_REDUCE_INTRINSIC (false|true)/#define USE_REDUCE_INTRINSIC {string}/g' RV.h",
        shell=True).returncode == 0
    os.chdir(oldWorkDir)


def setRV(cond):
    oldWorkDir = os.getcwd()
    os.chdir("AdaptiveCpp/include/hipSYCL")
    string = "true" if cond else "false"
    assert subprocess.run(f"sed -i -E 's/#define USE_RV (false|true)/#define USE_RV {string}/g' RV.h",
                          shell=True).returncode == 0
    os.chdir(oldWorkDir)


def setIncompleteSgsOpt(cond):
    oldWorkDir = os.getcwd()
    os.chdir("AdaptiveCpp/include/hipSYCL")
    string = "true" if cond else "false"
    assert subprocess.run(
        f"sed -i -E 's/#define INCOMPLETE_SGS_OPT (false|true)/#define INCOMPLETE_SGS_OPT {string}/g' RV.h",
        shell=True).returncode == 0
    os.chdir(oldWorkDir)


def setWgSSCPOpt(cond):
    oldWorkDir = os.getcwd()
    os.chdir("AdaptiveCpp/include/hipSYCL")
    string = "true" if cond else "false"
    assert subprocess.run(f"sed -i -E 's/#define WG_SSCP_OPT (false|true)/#define WG_SSCP_OPT {string}/g' RV.h",
                          shell=True).returncode == 0
    os.chdir(oldWorkDir)


os.environ["PATH"] += ":" + os.sep.join([os.getcwd() + "install/bin"])
os.environ["PATH"] += ":" + os.sep.join([os.getcwd() + "/install/lib/cmake"])
os.environ["HOME"] = os.getcwd()
os.environ["OMP_PROC_BIND"] = "TRUE"

gitclone("https://github.com/moritz-2001/AdaptiveCpp.git", "AdaptiveCpp", "tags/bachelor-thesis")
gitclone("https://github.com/moritz-2001/portblas.git", "portblas", "tags/thesis")
gitclone("https://github.com/moritz-2001/sycl-bench.git", "sycl-bench", "tags/thesis")
gitclone("https://github.com/moritz-2001/ethminer", "velocity", "tags/thesis")

results = []
for sgSize in [32, 64, 8, 16]:
    for compilerOption in ["generic", "omp"]:
        for variant in ["rv", "cbs"]:
            change_sg_size(sgSize)
            setRV(True if variant == "rv" else False)

            compilerOption = "generic" if compilerOption == "generic" else ("rv" if variant == "rv" else "omp")
            buildAll(compilerOption, True, sgSize, True, True, sgSize == 32 or sgSize == 64)
            results += benchmarks(compilerOption, variant, sgSize)

change_sg_size(32)

setIncompleteSgsOpt(False)
setWgSSCPOpt(False)
for variant in ["rv", "cbs"]:
    for compilerOption in ["generic", "omp"]:
        compilerOption = "generic" if compilerOption == "generic" else ("rv" if variant == "rv" else "omp")
        setRV(True if variant == "rv" else False)
        buildAll(compilerOption, True, 32, True, True, True)
        results += benchmarks(compilerOption, variant, 32, "-wo-wg-and-sg-opt")
setIncompleteSgsOpt(True)
setWgSSCPOpt(True)

setIncompleteSgsOpt(False)
for variant in ["rv", "cbs"]:
    setRV(True if variant == "rv" else False)
    buildAll("generic", True, 32, True, True, True)
    results += benchmarks("generic", variant, 32, "-only-wg-opt")
setIncompleteSgsOpt(True)

setIncompleteSgsOpt(True)
setWgSSCPOpt(True)
setUseReduceIntrinsic(False)
for variant in ["cbs", "rv"]:
    setRV(True if variant == "rv" else False)
    buildAll("generic", True, 32, True, False)
    results += benchmarksWithoutReduceIntrinsic("generic", variant)

# Upstream CBS sg-size one
gitclone("", "AdaptiveCpp", "tags/bachelor-thesis-sg-one")
gitclone("", "portblas", "tags/thesis-sg-size-one")

for compilerOption in ["generic"]:
    buildAll(compilerOption, True, 1)
    results += benchmarks(compilerOption, "upstream", 1)

print(json.dumps(results))
