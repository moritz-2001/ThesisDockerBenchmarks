#!/usr/bin/python3

import seaborn as sns
import matplotlib.pyplot as plt
import pandas as pd
import json
plt.rcParams.update({'font.size': 14})
import sys

def read(file):
    s = open(file, 'r').read()
    return json.loads(s)


if len(sys.argv) <= 2:
    print("createGraph file machineName...")
    print("For example: python3 createGraph.py results/zen4.json zen4")
    exit(1)

data = {
    "name": [],
    "arch": [],
    "time": [],
    "variant": [],
    "compilerPass": [],
    "SG-Size": [],
    "data-type": [],
    "uses-intrinsic": [],
    "wo-wg-and-sg-opt": [],
    "only-wg-opt": [],
    "only-sg-opt": [],
}
pd.DataFrame(data)

def fill(arch, machineData):
    for e in machineData:
        e = e[0]
        if e["time"] == "" and e["throughput"] == "":
            continue

        data["uses-intrinsic"] += [False if "without" in e["name"] else True]

        data["wo-wg-and-sg-opt"] += [True if "wo-wg-and-sg-opt" in e["name"] else False]
        data["only-wg-opt"] += [True if "only-wg-opt" in e["name"] else False]
        data["only-sg-opt"] += [True if "only-sg-opt" in e["name"] else False]

        if "-wo-wg-and-sg-opt" in e["name"]:
            data['name'] += [e['name'].replace("-wo-wg-and-sg-opt", "")]
        elif  "-only-wg-opt" in e["name"]:
            data['name'] += [e['name'].replace("-only-wg-opt", "")]
        elif "-only-sg-opt" in e["name"]:
            data['name'] += [e['name'].replace("-only-sg-opt", "")]
        elif "-without-reduce-intrinsic" in e["name"]:
            data['name'] += [e['name'].replace("-without-reduce-intrinsic", "")]
        else:
            data['name'] += [e['name']]

        data["arch"] +=[arch]

        if e["throughput"] != "":
            e["time"] = str(1 / float(e["throughput"]))

        data["time"] += [float(e["time"]) * 1000] if "sycl-bench" in e['name'] else [float(e["time"]) / 10**6]

        data["variant"] += [e["Variant"]]
        data["compilerPass"] += [e["compilerPass"]]
        data["SG-Size"] += [e["SG-Size"]]
        data["data-type"] += [e["data-type"]]

fill(sys.argv[2], read(sys.argv[1]))
df = pd.DataFrame(data)

def isSpecialCase(x):
    return x["only-wg-opt"] or x["only-sg-opt"] or not x["uses-intrinsic"] or x["wo-wg-and-sg-opt"]

def isEhtminer(x):
    return x["name"] == "ethminer"

def isPortblas(x):
    return x["name"] == "portblas-iamax-4194304" or x["name"] == "portblas-ger-8192"

def isOtherBench(x):
    return isPortblas(x) or isEhtminer(x)


def filter_one(x):
    if isSpecialCase(x):
        return False

    if isOtherBench(x):
        return True

    return x["data-type"] in ["fp64", "bool"]

def geoMean():
    wos = df[df.apply(lambda x: filter_one(x), axis=1)]
    cond = (wos.compilerPass == "SSCP") & (wos["SG-Size"] == 32)
    def speedUp(x):
        cond2 = cond & (wos.variant == "cbs") & (wos.name == x["name"]) & (wos.arch == x["arch"])
        if not len(wos[cond2]["time"].values) == 1:
            print(wos[cond2])
        assert len(wos[cond2]["time"].values) == 1
        speedup = wos[cond2]["time"].values[0] / x["time"]
        x["time"] = speedup
        return x

    def isBaseLine(x):
        cond2 = cond & (wos.variant == "cbs") & (wos.name == x["name"]) & (wos.arch == x["arch"])
        return (wos[cond2].values[0] == x.values).all()

    res = wos[wos.apply(lambda x: not isBaseLine(x), axis=1)]
    return pd.DataFrame(res[(res.compilerPass == "SSCP")].transform(speedUp, axis=1))

def plotWFVvsCBS():
    res = geoMean()
    # Filter and group the data
    wos = res[res.apply(filter_one, axis=1)]
    wos = wos.replace({"portblas-ger-8192":"portblas-ger", "portblas-iamax-4194304": "portblas-iamax"})
    wos = wos.sort_values(by="name")
    cond = (wos.compilerPass == "SSCP") & (wos["SG-Size"] == 32)
    wos = wos[cond]

    fig, ax = plt.subplots(figsize=(20, 15))
    # Plotting
    sns.barplot(ax=ax, x='name', y='time', hue='arch', data=wos, legend=True)
    for container in ax.containers:
        ax.bar_label(container, fmt='%.1f')

    ax.set(xlabel="Benchmark", ylabel="WFV geomean speedup over H-CBS")
    ax.set_yscale('log')
    plt.xticks(rotation=90)
    plt.tight_layout()
    plt.savefig('wfv_vs_hcbs.png')

plotWFVvsCBS()


def filter_one(x):
    if isSpecialCase(x):
        return False

    if x["name"] == "portblas-iamax-4194304":
        return True
    if x["name"] == "portblas-ger-8192":
        return True

    if "_upstream" in x["name"]:
        return False

    if "sg" in x["name"]:
        return False

    return x["data-type"] in ["fp64", "bool"]

def geoMean(compilerPass):
    wos = df[df.apply(filter_one, axis=1)]
    def speedUp(x):
        cond = (wos["SG-Size"] == 1) & (wos.variant == "upstream") & (wos.compilerPass == compilerPass) & (wos.name == x["name"]) & (wos.arch == x["arch"])

        assert len(wos[cond]["time"].values) == 1
        speedup = min(wos[cond]["time"]) / x["time"]
        x["time"] = speedup
        return x

    def isBaseLine(x):
        cond = (wos["SG-Size"] == 1) & (wos.variant == "upstream") & (wos.compilerPass == compilerPass) & (wos.name == x["name"]) & (wos.arch == x["arch"])
        return (wos[cond].values[0] == x.values).all()

    withoutBaseLine = wos[wos.apply(lambda x: not isBaseLine(x), axis=1)]
    return pd.DataFrame(withoutBaseLine[(withoutBaseLine.compilerPass == compilerPass)].transform(speedUp, axis=1))


def compareWithUpstream(title, filter):
    res = geoMean("SSCP")
    pdF = res[res.apply(filter, axis=1)]
    pdF = pdF.replace({"portblas-ger-8192":"portblas-ger", "portblas-iamax-4194304": "portblas-iamax"})
    pdF = pdF.replace({"cbs":"H-CBS"})
    pdF = pdF.replace({"rv":"WFV"})

    cond =  (pdF.compilerPass == "SSCP") & ((pdF["SG-Size"] == 32) | (pdF["SG-Size"] == 1))
    pdF = pdF[cond]
    dfGrouped = pdF[cond].groupby(
        ["name"])

    fig, axes = plt.subplots(nrows=int(len(dfGrouped) / 2), ncols=int(2), tight_layout=True, figsize=(12, 12), sharey=True)
    fig.suptitle(title)
    plt.subplots_adjust(hspace=None)

    fig.set_figwidth(24)
    fig.legend("a")
    for i, (name, group) in enumerate(dfGrouped):
        ax = axes[int(i / 2), int(i % 2)]
        bar_plot = sns.barplot(ax=ax, x='arch', y='time', hue="variant", data=group, legend=True)
        for container in bar_plot.containers:
            bar_plot.bar_label(container, fmt='%.1f')
        ax.set(xlabel=name[0], ylabel="Geomean speedup")
    plt.yscale("log")
    plt.tight_layout()
    plt.savefig('all.png')


compareWithUpstream("", filter_one)
