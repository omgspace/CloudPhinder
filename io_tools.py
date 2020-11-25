## from builtin
import h5py
from os import path,getcwd,mkdir
from glob import glob
import numpy as np
from collections import OrderedDict

## from github/mikegrudic
from Meshoid import Meshoid

## from GIZMO
import load_from_snapshot #routine to load snapshots from GIZMo files

def make_input(
    snapshots="snapshot_000.hdf5",
    outputfolder='None',
    ptype=0,
    G=4.301e4,
    cluster_ngb=32,
    nmin=1,
    softening=1e-5,
    alpha_crit=2,
    np=1,
    ntree=10000,
    overwrite=False,
    units_already_physical=False,
    max_linking_length=1e100):

    if (not isinstance(snapshots, list)):
        snapshots=[snapshots]

    arguments={
        "<snapshots>": snapshots,
        "--outputfolder": outputfolder,
        "--ptype": ptype,
        "--G": G,
        "--cluster_ngb": cluster_ngb,
        "--nmin": nmin,
        "--softening": softening,
        "--alpha_crit": alpha_crit,
        "--np": np,
        "--ntree": ntree,
        "--overwrite": overwrite,
        "--units_already_physical": units_already_physical,
        "--max_linking_length": max_linking_length
        }
    return arguments

def parse_filepath(filepath,outputfolder):
def make_input(
    # we have a lone snapshot, no snapdir, find the snapshot number and snapdir
    if ".hdf5" in filepath: 
        snapnum = int(filepath.split("_")[-1].split(".hdf5")[0].split(".")[0].replace("/",""))
        snapname = filepath.split("_")[-2].split("/")[-1]
        snapdir = "/".join(filepath.split("/")[:-1])
        if outputfolder == "None": outputfolder = snapdir #getcwd() + "/".join(filepath.split("/")[:-1])

    # filepath refers to the directory in which the snapshot's multiple files are stored
    else: 
        snapnum = int(filepath.split("snapdir_")[-1].replace("/",""))
        print(filepath)
        snapname = glob(filepath+"/*.hdf5")[0].split("_")[-2].split("/")[-1] #"snapshot" #filepath.split("_")[-2].split("/")[-1]
        print(snapname)
        snapdir = filepath.split("snapdir")[0] + "snapdir" + filepath.split("snapdir")[1]
        if outputfolder == "None": outputfolder = getcwd() + filepath.split(snapdir)[0]

    ## handle instances of non-default outputfolder 
    if outputfolder == "": outputfolder = "."
    if outputfolder is not "None":
        if not path.isdir(outputfolder):
            mkdir(outputfolder)
         
    if not snapdir:
        snapdir = getcwd()
        print('Snapshot directory not specified, using local directory of ', snapdir)

    ## check detected configuration for consistency
    fname_found, _, _ =load_from_snapshot.check_if_filename_exists(
        snapdir,
        snapnum,
        snapshot_name=snapname)
    if fname_found!='NULL':    
        print('Snapshot ', snapnum, ' found in ', snapdir)
    else:
        print('Snapshot ', snapnum, ' NOT found in ', snapdir, '\n Skipping it...')
        return None,None,None
 
    return snapnum, snapdir, snapname, outputfolder

def read_particle_data(
    snapnum,
    snapdir,
    snapname,
    cluster_ngb):
    
    ## create a dummy return value that the calling function can 
    ##  check against
    dummy_return = tuple([None]*10)

    ## determine if there are even enough particles in this snapshot to try and
    ##  find clusters from
    npart = load_from_snapshot.load_from_snapshot(
        "NumPart_Total",
        "Header",
        snapdir,
        snapnum,
        snapshot_name=snapname)[ptype]
    print(npart)
    if npart < cluster_ngb:
        print("Not enough particles for meaningful cluster analysis!")
        return dummy_return
    
    #Read gas properties
    keys = load_from_snapshot.load_from_snapshot(
        "keys",
        ptype,
        snapdir,
        snapnum,
        snapshot_name=snapname)
    if keys is 0:
        print("No keys found, noping out!")        
        return dummy_return

    # now we refine by particle density, by applying a density mask `criteria`
    criteria = np.ones(npart,dtype=np.bool) 
    if "Density" in keys:
        rho = load_from_snapshot.load_from_snapshot(
            "Density",
            ptype,
            snapdir,
            snapnum,
            snapshot_name=snapname,
            units_to_physical=(not units_already_physical))

        if len(rho) < cluster_ngb:
            print("Not enough particles for meaningful cluster analysis!")
            return dummy_return

    # we have to do a kernel density estimate for e.g. dark matter or star particles
    else: 
        m = load_from_snapshot.load_from_snapshot(
            "Masses",
            ptype,
            snapdir,
            snapnum,
            snapshot_name=snapname)

        if len(m) < cluster_ngb:
            print("Not enough particles for meaningful cluster analysis!")
            return dummy_return

        x = load_from_snapshot.load_from_snapshot(
            "Coordinates",
            ptype,
            snapdir,
            snapnum,
            snapshot_name=snapname)

        print("Computing density using Meshoid...")
        rho = Meshoid(x,m,des_ngb=cluster_ngb).Density()
        print("Density done!")

    # only look at dense gas (>nmin cm^-3)
    criteria = np.arange(len(rho))[rho*404 > nmin] 

    print("%g particles denser than %g cm^-3" % (criteria.size,nmin))  #(np.sum(rho*147.7>nmin), nmin))
    if not criteria.size > cluster_ngb:
        print('Not enough /dense/ particles, exiting...')
        return dummy_return

    ## apply the mask and sort by descending density
    rho = np.take(rho, criteria, axis=0)
    rho_order = (-rho).argsort() ## sorts by descending density
    rho = rho[rho_order]

    # now let's store all particle data that satisfies the criteria
    particle_data = {"Density": rho} 

    ## load up the unloaded particle data
    for k in keys:
        if not k in particle_data.keys():
            particle_data[k] = load_from_snapshot.load_from_snapshot(
                k,ptype,
                snapdir,snapnum,
                snapshot_name=snapname,
                particle_mask=criteria,
                units_to_physical=(not units_already_physical))[rho_order]

    ## unpack the particle data into some variables
    m = particle_data["Masses"]
    x = particle_data["Coordinates"]
    ids = particle_data["ParticleIDs"] 

    u = (particle_data["InternalEnergy"] if ptype == 0 else np.zeros_like(m))
    if "MagneticField" in keys:
        energy_density_code_units = np.sum(particle_data["MagneticField"]**2,axis=1) / 8 / np.pi * 5.879e9
        specific_energy = energy_density_code_units / rho
        u += specific_energy
        
    zz = (particle_data["Metallicity"] if "Metallicity" in keys else np.zeros_like(m))
    v = particle_data["Velocities"]

    sfr = particle_data["StarFormationRate"] if "StarFormationRate" in keys else sfr = np.zeros_like(m)

    ## handle smoothing length options
    if "AGS-Softening" in keys:
        hsml = particle_data["AGS-Softening"]
    elif "SmoothingLength" in keys:
        hsml = particle_data["SmoothingLength"] 
    else:
        hsml = np.ones_like(m)*softening
        
    # potential doesn't get used anymore, so this is moot
    if "Potential" in keys: 
        phi = particle_data["Potential"] #load_from_snapshot.load_from_snapshot("Potential",ptype,snapdir,snapnum, particle_mask=criteria)
    else:
        phi = np.zeros_like(m)

    return (x, m, rho,
        phi, hsml, u,
        v, zz, sfr,
        particle_data)

def computeAndDump(
    particle_data,
    ptype,
    bound_groups,
    hdf5_outfilename,
    dat_outfilename,
    overwrite):

    print("Time: %g"%t)
    print("Done grouping. Computing group properties...")

    ## sort the clouds by descending mass
    groupmass = np.array([m[c].sum() for c in bound_groups.values() if len(c)>3])
    groupid = np.array([c for c in bound_groups.keys() if len(bound_groups[c])>3])
    groupid = groupid[groupmass.argsort()[::-1]]

    bound_groups = OrderedDict(zip(groupid, [bound_groups[i] for i in groupid]))

    #groupsfr = np.array([sfr[c].sum() for c in bound_groups.values() if len(c)>3])
    #print("Total SFR in clouds: ",  groupsfr.sum())

    # Now we dump their properties
    bound_data = OrderedDict()
    bound_data["Mass"] = []
    bound_data["Center"] = []
    bound_data["PrincipalAxes"] = []
    bound_data["Reff"] = []
    bound_data["HalfMassRadius"] = []
    bound_data["NumParticles"] = []
    bound_data["VirialParameter"] = []
    
    
    print("Outputting to: ",hdf5_outfilename)
    ## dump to HDF5
    with h5py.File(hdf5_outfilename, 'w') as Fout:

        i = 0
        fids = ids
        #Store all keys in memory to reduce I/O load

        for k,c in bound_groups.items():
            ## calculate some basic properties of the clouds to output to 
            ##  the .dat file
            bound_data["Mass"].append(m[c].sum())
            bound_data["NumParticles"].append(len(c))
            bound_data["Center"].append(np.average(x[c], weights=m[c], axis=0))

            ## find principle axes
            dx = x[c] - bound_data["Center"][-1]
            eig = np.linalg.eig(np.cov(dx.T))[0]
            bound_data["PrincipalAxes"].append(np.sqrt(eig))

            ## find half mass radius, assumes all particles have 
            ##  same mass
            r = np.sum(dx**2, axis=1)**0.5
            bound_data["HalfMassRadius"].append(np.median(r))
        
            bound_data["Reff"].append(np.sqrt(5./3 * np.average(r**2,weights=m[c])))
            bound_data["VirialParameter"].append(VirialParameter(c, x, m, hsml, v, u))

            cluster_id = "Cloud"+ ("%d"%i).zfill(int(np.log10(len(bound_groups))+1))

            ## dump particle data for this cloud to the hdf5 file
            Fout.create_group(cluster_id)
            for k in keys: 
                Fout[cluster_id].create_dataset('PartType'+str(ptype)+"/"+k, data = particle_data[k].take(c,axis=0))
            i += 1

        print("Done grouping bound clusters!")

    ## dump basic properties to .dat file
    SaveArrayDict(dat_outfilename, bound_data)

def SaveArrayDict(path, arrdict):
    """Takes a dictionary of numpy arrays with names as the keys and saves them in an ASCII file with a descriptive header"""
    header = ""
    offset = 0
    
    for i, k in enumerate(arrdict.keys()):
        if type(arrdict[k])==list: arrdict[k] = np.array(arrdict[k])
        if len(arrdict[k].shape) == 1:
            header += "(%d) "%offset + k + "\n"
            offset += 1
        else:
            header += "(%d-%d) "%(offset, offset+arrdict[k].shape[1]-1) + k + "\n"
            offset += arrdict[k].shape[1]
            
    data = np.column_stack([b for b in arrdict.values()])
    data = data[(-data[:,0]).argsort()] 
    np.savetxt(path, data, header=header,  fmt='%.15g', delimiter='\t')
