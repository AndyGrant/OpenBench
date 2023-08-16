import os
import json
import tempfile
import subprocess

if __name__ == "__main__":
    root = os.getcwd()
    engines = os.path.join(root, "Engines")
    configs = {}

    # get all engine config files
    config_files = [file for file in os.scandir(os.path.join(root, "Engines")) if file.is_file()]

    # create temporary working directory
    with tempfile.TemporaryDirectory() as path:
        os.chdir(path)

        for file in config_files:
            with open(file.path, "r") as f:
                data = f.read()
                obj = json.loads(data)

                # get engine info
                source = obj["source"]
                base_branch = obj["base"]
                makefile_path = obj["build"]["path"]
                name = source.split('/')[-1]

                print(f"Cloning [{name}/{base_branch}]...")
                os.chdir(path)
                subprocess.run(
                    ["git", "clone", source, "-b", base_branch, "--single-branch", "--depth", "1", "--quiet"],
                    stdout=subprocess.DEVNULL
                )

                try:
                    print("Compiling...")
                    make_path = os.path.join(path, name, makefile_path)
                    os.chdir(make_path)
                    subprocess.run(["make", "EXE=temp"], stdout=subprocess.DEVNULL)

                    print("Running Bench...")
                    try:
                        if os.name == 'nt':
                            exe = "temp.exe"
                        else:
                            exe = "./temp"
                        result = subprocess.run([exe, "bench"], stdout=subprocess.PIPE)
                        bench_line = result.stdout.decode('utf-8').strip().split('\n')[-1]
                        print(bench_line)
                        old_nps = str(obj["nps"])
                        obj["nps"] = int(bench_line.split(' ')[-2])
                        configs[file.name] = (old_nps, obj)
                    except:
                        print("Couldn't run bench!")
                        configs[file.name] = None
                except:
                    print("Couldn't compile!\n")
                    configs[file.name] = None
                    continue

                print("")

        os.chdir(root)

    # overwrite files and print summary
    for file in config_files:
        config = configs[file.name]
        if config != None:
            with open(file.path, "w") as f:
                nps = config[1]["nps"]
                print(f"{file.name.split('.')[0]: <12}: {config[0]: <8} -> {nps: >8}")
                f.write(json.dumps(config[1], indent=4))
        else:
            print(f"{file.name.split('.')[0]: <12}: An error occurred!")
