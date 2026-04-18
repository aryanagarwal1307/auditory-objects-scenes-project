import os
import json
import shutil
import pandas as pd
import numpy as np
import argparse
import sys
from scipy.io import loadmat

# Helper function to find the files we need to rename
def find_files(directory):

    # Choose all non '.' files in the directory
    files = [f for f in os.listdir(directory) if f.endswith('.json') or f.endswith('.nii') or f.endswith('.tsv') or f.endswith('.mat')]
    files = [f for f in files if 'practice' not in f and 'order' not in f]

    # Sort so that we rename nii files first (allows JSON reference with same name)
    files = sorted(files, key=lambda x: (x.endswith('.json'), x))

    for file in files:
        if verbose:
            print(file)

    return files


# Helper function to transform .mat files to TSV files
def transform_mat_to_tsv(path_to_events_file, directory, execute, verbose):
    # read data from nested .mat structure
    events = loadmat(file_name=path_to_events_file)
    onset = events['data']['Onsets'][0][0]
    duration = events['data']['Durations'][0][0]
    stimulus_name = events['data']['trialType'][0][0]

    # convert values to arrays
    onset = np.concatenate(onset).ravel()
    duration = np.concatenate(duration).ravel()
    stimulus_name = np.concatenate(stimulus_name).ravel()

    # create panda with columns onset duration and stimulus name
    events_panda = pd.DataFrame({'onset': onset, 'duration': duration, 'trial_type': stimulus_name})

    # Save the file as a tsv with the same name
    print(f"Ready to save {path_to_events_file} as a tsv")
    if execute:
        temp_path = os.path.join(directory, os.path.basename(path_to_events_file).replace(".mat", ".tsv"))
        events_panda.to_csv(temp_path, sep='\t', index=False)
        print(f"saved to {temp_path}")
    if verbose: print(events_panda)

    return 0


def find_json(directory, files, run):
    if run == "0":
        print("This is the practice run")
        x = "practice"
    else:
        x = f"run-{run}"

    for file in files:
        if file.endswith('.json'):
            with open(os.path.join(directory, file), 'r') as json_file:
                json_data = json.load(json_file)
                if x in json_data['SeriesDescription']:
                    return file
    return 0


def rename(directory, files, execute, verbose):
    names = []
    # loop over every file to be renamed
    for filename in files:
        file_path = os.path.join(directory, filename)

        # This conditional sets the path to reference the .json where the "code" is extracted form
        # The code specifies the type of scan and for nii files we reference the json for extraction

        if filename.endswith('.json'):
            json_path = file_path
        elif filename.endswith('.nii'):
            json_path = os.path.join(directory, f"{filename.split('.')[0]}.json")
        elif filename.endswith('.tsv'):
            json_path = os.path.join(directory, find_json(directory, files, filename.split("_")[2]))
        elif filename.endswith('.mat'):
            json_path = os.path.join(directory, find_json(directory, files, filename.split("_")[2]))

        with open(json_path, 'r') as json_file:
            json_data = json.load(json_file)
            code = json_data['SeriesDescription']
            # This conditional adds the acquisition time to audio test file names so if we repeat then we don't over write files
            if 'audiotest' in code:
                acq_time = f"_{json_data['AcquisitionTime']}"
            else:
                acq_time = ""

        # These conditionals allow for specific formatting (according to BIDS) for the various scans
        if 'anat' in code:
            # This is an anatomical run
            new_path = f"sub-{filename.split('_')[0]}_{code}.{filename.split('.')[-1]}"
        elif 'Scout' in code:
            # This is a scout run
            new_path = f"sub-{filename.split('_')[0]}_{code}_scout.{filename.split('.')[-1]}"
        elif 'epi' in code:
            # This is a fieldmap
            new_path = f"sub-{filename.split('_')[0]}_{code}.{filename.split('.')[-1]}"
        else:
            # This is a functional run or the .csv file for the run or the .mat file for the run (including audio test)
            if filename.endswith('.nii') or filename.endswith('.json'): # the nii data or jsons
                new_path = f"sub-{filename.split('_')[0]}_{code}_bold{acq_time}.{filename.split('.')[-1]}"
            elif filename.endswith('.tsv') or filename.endswith('.mat'): # events files
                new_path = f"sub-{json_path.split('/')[-1].split('_')[0]}_{code}_events{acq_time}.{filename.split('.')[-1]}"

        # Conditional to rename/print.
        if execute:
            os.rename(file_path, os.path.join(directory, new_path))
            if verbose: print(f"{filename} renamed to {new_path}")
        else:
            if verbose: print(new_path)
        names.append(new_path)
    print("Names have been assigned")

    return names


def move(subject_number, niidir, datadir, execute, verbose):
    subject_id = "sub-mm" + subject_number
    subject_dir = datadir + "/" + subject_id
    if execute:
        if os.path.exists(datadir):
            os.chdir(datadir)
        else:
            os.makedirs(datadir)
            os.chdir(datadir)

    maps = {'scout': 'other', 'practice': 'other', 'order': 'other', 'audiotest': 'other', 'anat': 'anat',
            'run': 'func', 'epi': 'fmap'}

    for file in os.listdir(niidir):
        for val in maps.keys():
            if val in file:
                if val == 'run' and '.mat' in file: # Moves .mat events to other instead of func
                    dest = 'other'
                else:
                    dest = maps[val]
                if execute:
                    if not os.path.exists(f"{subject_dir}/{dest}"): os.makedirs(f"{subject_dir}/{dest}")
                    shutil.move(os.path.join(niidir, file), f"{subject_dir}/{dest}")
                if verbose: print(f"{file} sent to {dest}")
                break
    if execute:
        os.chdir(subject_dir)
        shutil.move(f"{subject_dir}/other", f"{datadir}/sourcedata/{subject_id}/other")
    else:
        if verbose: print(f"Would have moved {subject_dir}/other to {datadir}/sourcedata/{subject_id}/other")
    return 1


def format_json(subject_number, bids_dir, verbose):
    """
    This function formats JSON files for field map files, functional files, and anatomical files
    Functional: Adds 'TaskName', deletes 'AcquisitionDuration'
    Anatomical: Deletes 'RepetitionTime'
    Field maps: Adds 'IntendedFor', deletes 'RepetitionTime', fixes j and j-
    """

    path_func = bids_dir + "/sub-mm" + subject_number + "/func"
    path_anat = bids_dir + "/sub-mm" + subject_number + "/anat"
    fmap_1 = bids_dir + "/sub-mm" + subject_number + "/fmap/" + "sub-mm" + subject_number + "_dir-AP_epi.json"
    fmap_2 = bids_dir + "/sub-mm" + subject_number + "/fmap/" + "sub-mm" + subject_number + "_dir-PA_epi.json"

    for file in os.listdir(path_func):
        if file.endswith(".nii"):
            # Edit the first fieldmap JSON. Add IntendedFor and delete repetition time
            with open(fmap_1, 'r') as json_file_1:
                json_data_1 = json.load(json_file_1)

            if 'IntendedFor' not in json_data_1: json_data_1['IntendedFor'] = []
            json_data_1['IntendedFor'].append(f"func/{file}")

            if 'RepetitionTime' in json_data_1: del json_data_1['RepetitionTime']

            if 'PA' in json_data_1['SeriesDescription']:
                json_data_1['PhaseEncodingDirection'] = "j"

            with open(fmap_1, 'w') as json_file_1:
                json.dump(json_data_1, json_file_1)

            # Edit the second fieldmap JSON. Add IntendedFor and delete repetition time
            with open(fmap_2, 'r') as json_file_2:
                json_data_2 = json.load(json_file_2)

            if 'IntendedFor' not in json_data_2: json_data_2['IntendedFor'] = []
            json_data_2['IntendedFor'].append(f"func/{file}")

            if 'RepetitionTime' in json_data_2: del json_data_2['RepetitionTime']

            if 'PA' in json_data_2['SeriesDescription']:
                json_data_2['PhaseEncodingDirection'] = "j"

            with open(fmap_2, 'w') as json_file_2:
                json.dump(json_data_2, json_file_2)

            if verbose: print(f"Fieldmap jsons updated for {file}")
        elif file.endswith(".json"):
            # Edit the function JSON files. Add in TaskName and remove AcquisitionDuration
            with open(os.path.join(path_func, file), 'r') as func_json:
                func_data = json.load(func_json)

            func_data['TaskName'] = 'multisensorymemory'
            if 'AcquisitionDuration' in func_data: del func_data['AcquisitionDuration']

            with open(os.path.join(path_func, file), 'w') as func_json:
                json.dump(func_data, func_json)

            if verbose: print(f"Fieldmap jsons updated for {file}")

    for file in os.listdir(path_anat):
        # Edit the anatomical data JSON files. Remove repetition time.
        if file.endswith(".json"):
            with open(os.path.join(path_anat, file), 'r') as anat_json:
                anat_data = json.load(anat_json)

            if 'RepetitionTime' in anat_data: del anat_data['RepetitionTime']

            with open(os.path.join(path_anat, file), 'w') as anat_json:
                json.dump(anat_data, anat_json)

            print(f"Anatomical JSON edited for {file}")

    print("Formatting of JSONs is done")

    return 0


def format_events(subject_number, bids_dir, descriptions, levels_dict, execute, verbose):
    """
    This function creates the required .json files for each .tsv events file which describe the column headers.

    Inputs:
    bids_dir: Path to the BIDS dataset
    descriptions: The description field as a dictionary for the .json file
    levels_dict: The levels field as a dictionary for the .json file

    Output:
    If execute = True, it will update the SON event files
    Otherwise, it will print out path to JSON files and the data to be sent to them
    """

    path = bids_dir + "/sub-mm" + subject_number + "/func"

    for file in os.listdir(path):
        if file.endswith(".tsv"):
            # Loading events file
            temp = pd.read_csv(os.path.join(path, file), sep='\t')

            # Creating the required JSON files
            data_dict = {}
            for column in temp.columns:
                data_dict[column] = {"Description": f"{descriptions[column]}"}
                if column in levels_dict.keys(): data_dict[column]["Levels"] = levels_dict[column]

            json_filename = os.path.splitext(os.path.join(path, file))[0] + ".json"

            if execute:
                # Write a new .json file
                with open(json_filename, 'w') as f:
                    json.dump(data_dict, f)

                if verbose: print(f"Events file updated and JSON created for {file}")
            else:
                if verbose: print(json_filename)
                if verbose: print(data_dict)

    return 0


def fix_anat(bids_dir, subject_number, execute, verbose):
    path = bids_dir + "/sub-mm" + subject_number + "/anat"

    for file in os.listdir(path):
        if 'T2w' in file:
            new_file = f"{file.split('_')[0]}_{file.split('_')[1]}.{file.split('.')[-1]}"
            new_file = new_file.replace("anat-", "")
            if execute: os.rename(os.path.join(path, file), os.path.join(path, new_file))
            if verbose: print(f"{file} renamed to {new_file}")
        elif 'T1w' in file:
            new_file = file
            new_file = new_file.replace("anat-", "")
            if execute: os.rename(os.path.join(path, file), os.path.join(path, new_file))
            if verbose: print(f"{file} renamed to {new_file}")

    return 0


if __name__ == "__main__":

    ############ Parse CL args ###############
    parser = argparse.ArgumentParser()
    parser.add_argument("-sub", "--subject_id", type=str, help="multimodal_sub_01", default="002")
    parser.add_argument('-u', '--user', type=str, default="aa2842")
    parser.add_argument("-e", '--execute', type=int, default=1)
    parser.add_argument("-v", "--verbose", type=int, default=1)

    args = parser.parse_args()
    subject_number = args.subject_id
    execute = args.execute
    user = args.user
    verbose = args.verbose

    log_file = open(f"/gpfs/milgram/project/turk-browne/{user}/multisensory-memory-project/preprocessing/XNat_Interact/logs/renaming_log_sub-multimem{subject_number}.log", 'w')
    sys.stdout = log_file
    sys.stderr = log_file

    directory = f'/gpfs/milgram/scratch60/turk-browne/{user}/sandbox/mm{subject_number}_nii/'
    bids_dir = f'/gpfs/milgram/scratch60/turk-browne/{user}/sandbox/bids'

    mat_files = [f for f in os.listdir(directory) if f.endswith('.mat')]
    for mat_file in mat_files:
        transform_mat_to_tsv(os.path.join(directory, mat_file), directory, execute, verbose)

    files = find_files(directory)
    new_names = rename(directory, files, execute, verbose)
    move(subject_number, directory, bids_dir, execute, verbose)

    if execute: format_json(subject_number, bids_dir, verbose)

    levels_dict = {'stimulus_name': {'category 1': 'some explanation', 'category 2': 'some explanation'},
                   'event': {'category 1': 'some explanation', 'category 2': 'some explanation'},
                   'trial_type': {'category 1': 'some explanation', 'category 2': 'some explanation'}
                   }

    descriptions = {'onset': 'something', 'duration': 'something', 'tr': 'something', 'stimulus_name': 'something',
                    'event': 'something', 'trial_type': 'something'}

    if execute: format_events(subject_number, bids_dir, descriptions, levels_dict, execute, verbose)

    fix_anat(bids_dir, subject_number, execute, verbose)

    print("Completed renaming and moving to BIDS directory")



