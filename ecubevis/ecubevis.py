import numpy as np
from glob import glob
import xarray as xr
import hvplot.xarray 
import cartopy.crs as ccrs
import holoviews as hv
import matplotlib.colors as colors
from matplotlib.pyplot import figure, show, savefig, close, colorbar, subplots
from mpl_toolkits.axes_grid1 import make_axes_locatable

import warnings
warnings.simplefilter(action='ignore', category=FutureWarning)

__all__ = ['plot_ndcube',
           'slice_ndcube',
           'load_transform_mfdataset']


class style:
   BOLD = '\033[1m'
   END = '\033[0m'
    

def load_transform_mfdataset(dir_path, dim, transform_func=None, 
                             transform_params={}):
    """
    Read a multi-file distributed N-dimensional ``xarray`` dataset.

    Parameters
    ----------
    dir_path : str
        Path to the files. 
    dim : str
        Dimension to concatenate along.
    transform_func : function or None
        Transform function to be applied to each file before loading it. 
    transform_params : dict, optional
        Parameters of the transform function.

    Returns
    -------
    combined : xarray Dataset
        Combined dataset.

    Notes
    -----
    https://xarray.pydata.org/en/stable/io.html#reading-multi-file-datasets
    """
    def process_one_path(file_path):
        # use a context manager, to ensure the file gets closed after use
        with xr.open_dataset(file_path) as ds:
            if transform_func is not None:
                ds = transform_func(ds, **transform_params)
            # load all data from the transformed dataset, to ensure we can
            # use it after closing each original file
            ds.load()
            return ds

    dir_path = dir_path + '/*.nc'
    paths = sorted(glob(dir_path))
    datasets = [process_one_path(p) for p in paths]
    combined = xr.concat(datasets, dim)
    return combined


def check_coords(ndarray):
    standard_names = ['lat', 'lon', 'level', 'time']
    alternative_names = ['latitude', 'longitude', 'height', 'frequency']

    for c in ndarray.coords:
        if c not in standard_names + alternative_names:
            msg = f'Xarray Dataset/Dataarray contains unknown coordinates. '
            msg += f'Must be one of: {standard_names} or {alternative_names}'
            raise ValueError(msg)

    for i, altname in enumerate(alternative_names):
        if altname in ndarray.coords:
            ndarray = ndarray.rename({alternative_names[i]: standard_names[i]})
    return ndarray


def slice_ndcube(ndarray, slice_time=None, slice_level=None, slice_lat=None, 
                 slice_lon=None):
    """  
    Slice an N-dimensional ``xarray`` Dataset across its dimensions (time, level,
    lat or lon, if present). This function is able to wrap selection assuming 
    360 degrees, which is not strighformard with ``xarray``. 

    Parameters
    ----------
    ndarray : xarray Dataset
        Input N-dimensional dataset.
    slice_time : tuple of int or str or None, optional
        Tuple with initial and final values for slicing the time dimension. If 
        None, the array is not sliced accross this dimension.
    slice_level : tuple of int or None, optional
        Tuple with initial and final values for slicing the level dimension. If 
        None, the array is not sliced accross this dimension.
    slice_lat : tuple of int or None, optional
        Tuple with initial and final values for slicing the lat dimension. If 
        None, the array is not sliced accross this dimension.
    slice_lon : tuple of int or None, optional
        Tuple with initial and final values for slicing the lon dimension. If 
        None, the array is not sliced accross this dimension.

    Returns
    -------
    ndarray : xarray Dataset
        When any of the arguments ``slice_time``, ``slice_level``, 
        ``slice_lat``, ``slice_lon`` is defined (not None) the returned 
        ``ndarray`` is the sliced input. If the slicing arguments are None the
        function returns the input Dataset.

    """ 
    ndarray = check_coords(ndarray)
    if slice_time is not None and 'time' in ndarray.coords:
        if isinstance(slice_time, tuple) and isinstance(slice_time[0], str):
            ndarray = ndarray.sel(time=slice(*slice_time))
        elif isinstance(slice_time, tuple) and isinstance(slice_time[0], int):
            ndarray = ndarray.isel(time=slice(*slice_time))
    
    if slice_level is not None and 'level' in ndarray.coords:
        ndarray = ndarray.isel(level=slice(*slice_level))
    
    if slice_lat is not None and 'lat' in ndarray.coords:
        ndarray = ndarray.sel(dict(lat=ndarray.lat[(ndarray.lat > slice_lat[0]) & 
                                                   (ndarray.lat < slice_lat[1])]))
    
    if slice_lon is not None and 'lon' in ndarray.coords:
        # -180 to 180
        if ndarray.lon[0].values < 0:
            ndarray = ndarray.sel(dict(lon=ndarray.lon[(ndarray.lon > slice_lon[0]) & 
                                                       (ndarray.lon < slice_lon[1])]))
        # 0 to 360
        else:
            ndarray = lon_wrap_slice(ndarray, wrap=360, indices=(slice_lon[0], 
                                                                 slice_lon[1]))
    
    return ndarray


def plot_ndcube(data, interactive=True, variable=None, x='lon', y='lat',
                groupby=None, slice_time=(0, 2), slice_level=(0, 2),
                slice_lat=None, slice_lon=None, colorbar=True, cmap='Blues_r', 
                logz=False, share_dynamic_range=True, vmin=None, vmax=None, 
                projection=None, coastline=False, global_extent=False, 
                dynamic=True, dpi=80, plot_sizepx=800, widget_location='right', 
                verbose=True):
    """
    Plot an in-memory n-dimensional datacube. The datacube is loaded through 
    ``xarray`` and therefore supports formats such as NetCDF, IRIS or GRIB.

    Parameters
    ----------
    data : xarray Dataset/Dataarray or str
        ERA5 variable(s) as Xarray (in memory) variable or as a string with 
        the path to the corresponding NetCDF file. Expected dimensions: 
        4D array [time, level, lat, lon] or 3D array [time, lat, lon].
    interactive : bool optional
        Whether to plot using an interactive plot (using ``hvplot``) with a 
        slider across the dimension set by ``groupby`` or an static mosaic 
        (using ``matplotlib``). 
    variable : str or int or None, optional
        The name of the variable to be plotted or the index at which it is 
        located. If None, the first 3D or 4D variable is selected.
    slice_time : tuple of int or str or None, optional
        Tuple with initial and final values for slicing the time dimension. If 
        None, the array is not sliced accross this dimension.
    slice_level : tuple of int or None, optional
        Tuple with initial and final values for slicing the level dimension. If 
        None, the array is not sliced accross this dimension.
    slice_lat : tuple of int or None, optional
        Tuple with initial and final values for slicing the lat dimension. If 
        None, the array is not sliced accross this dimension.
    slice_lon : tuple of int or None, optional
        Tuple with initial and final values for slicing the lon dimension. If 
        None, the array is not sliced accross this dimension.
    colorbar : bool optional
        To show a colorbar.
    cmap : str optional
        Colormap, eg. RdBu_r, viridis.  
    projection : cartopy.crs projection
        According to Cartopy's documentation it can be one of the following
        (https://scitools.org.uk/cartopy/docs/latest/crs/projections.html): 
        PlateCarree, AlbersEqualArea, AzimuthalEquidistant, EquidistantConic, 
        LambertConformal, LambertCylindrical, Mercator, Miller, Mollweide, 
        Orthographic, Robinson, Sinusoidal, Stereographic, TransverseMercator, 
        UTM, InterruptedGoodeHomolosine, RotatedPole, OSGB, EuroPP, Geostationary, 
        NearsidePerspective, EckertI, EckertII, EckertIII, EckertIV, EckertV, 
        EckertVI, EqualEarth, Gnomonic, LambertAzimuthalEqualArea, 
        NorthPolarStereo, OSNI, SouthPolarStereo
    
    Notes
    -----
    https://github.com/pydata/xarray/issues/2199
    https://hvplot.holoviz.org/user_guide/Gridded_Data.html
    https://hvplot.holoviz.org/user_guide/Geographic_Data.html    

    TODO
    ----
    [1]
    https://unidata.github.io/MetPy/latest/examples/Four_Panel_Map.html
    https://scitools.org.uk/cartopy/docs/v0.13/matplotlib/advanced_plotting.html
    
    ax = plt.axes(projection=projection)
                if coastline:
                    ax.coastlines(resolution='10m')

                var_array_sliced[i].plot(cmap=cmap, vmin=vmin, vmax=vmax,
                                      transform=projection)
    
    [2]
    in subplots function:
    subplot_kw={'projection': ccrs.PlateCarree()}

    [3]
    for hvplot: col='time'
    https://hvplot.holoviz.org/user_guide/Subplots.html

    """     
    if isinstance(data, str):
        if not data.endswith('.nc'):
            data += '.nc'
        data = xr.open_dataset(data, engine="netcdf4", decode_times=True, 
                               chunks={'time': 1}) 
    
    if not isinstance(data, (xr.Dataset, xr.DataArray)):
        raise TypeError('`data` must be an Xarray Dataset/Dataarray')  
    
    if isinstance(data, xr.DataArray):
        data = data.to_dataset()

    ### Selecting the variable 
    if variable is None: # taking the first 3D or 4D data variable
        for i in data.data_vars:
            if data.data_vars.__getitem__(i).ndim >= 3:
                variable = i
    elif isinstance(variable, int):
        variable = list(data.keys())[variable]
    else: # otherwise it is the variable name as a string
        if not isinstance(variable, str):
            raise ValueError('`variable` must be None, int or str')
    
    ### Getting info
    shape = data.data_vars.__getitem__(variable).shape
    tini = data.data_vars.__getitem__(variable).time[0].values
    tini = np.datetime_as_string(tini, unit='m')
    tfin = data.data_vars.__getitem__(variable).time[-1].values
    tfin = np.datetime_as_string(tfin, unit='m')
    var_array = check_coords(data)
    var_array = slice_ndcube(var_array, slice_time, slice_level, slice_lat, 
                             slice_lon)
    
    ### Slicing the array variable
    var_array = var_array.data_vars.__getitem__(variable)
    
    if groupby is None:
        if interactive:
            groupby = ['time', 'level'] if var_array.ndim == 4 else 'time'
        else:
            groupby = 'time'
    
    if not var_array.ndim in [3, 4]:
        raise TypeError('Variable is neither 3D nor 4D')
 
    if verbose in [1, 2]:
        try:
            lname = var_array.long_name
            units = var_array.units
        except:
            lname = variable
            units = 'unknown' 
        shape_slice = var_array.shape
        # assuming the min temporal sampling unit is minutes
        tini_slice = np.datetime_as_string(var_array.time[0].values, unit='m')
        tfin_slice = np.datetime_as_string(var_array.time[-1].values, unit='m')
        dimp = '4D' if var_array.ndim == 4 else '3D'
        print(f'{style.BOLD}Name:{style.END} {variable}, {lname}')
        print(f'{style.BOLD}Units:{style.END} {units}') 
        print(f'{style.BOLD}Dimensionality:{style.END} {dimp}') 
        print(f'{style.BOLD}Shape:{style.END} {shape}')
        print(f'{style.BOLD}Shape (sliced array):{style.END} {shape_slice}')
        print(f'{style.BOLD}Time interval:{style.END} {tini} --> {tfin}')
        msg = 'Time interval (sliced array):'
        print(f'{style.BOLD}{msg}{style.END}{tini_slice} --> {tfin_slice}\n')
    if verbose in [2]:
        print(data.coords)
        print(data.data_vars, '\n')
    
    sizey = var_array.lat.shape[0]
    sizex = var_array.lon.shape[0]
    sizexy_ratio = sizex / sizey

    ### interactive plotting with slider(s) using bokeh
    if interactive:
        hv.extension('bokeh')
        if coastline or projection is not None:
            width = plot_sizepx
            height = width
        else:
            width = plot_sizepx
            height = int(np.round(width / sizexy_ratio))

        sizeargs = dict(height=height, width=width)
        project = False if projection is None else True
    
        return var_array.hvplot(kind='image', x=x, y=y, groupby=groupby, 
                                dynamic=dynamic, colorbar=colorbar, cmap=cmap, 
                                shared_axes=True, legend=True, logz=logz, 
                                widget_location=widget_location, 
                                project=project, projection=projection, 
                                global_extent=global_extent, 
                                coastline=coastline, **sizeargs)
        
    ### Static mosaic with matplotlib
    else:                
        if share_dynamic_range:
            if vmin is None:
                vmin = var_array.min().compute()
                vmin = np.array(vmin)
            if vmax is None:
                vmax = var_array.max().compute()   
                vmax = np.array(vmax)
        
        return plot_mosaic(var_array, show_colorbar=colorbar, dpi=dpi, 
                           cmap=cmap, logscale=logz, show_axis=True, save=None, 
                           vmin=vmin, vmax=vmax, transparent=False, 
                           coastline=coastline, projection=projection)
                

def plot_mosaic(ndarray, show_colorbar=True, dpi=100, cmap='viridis', 
                logscale=False, show_axis=True, save=None, vmin=None, vmax=None, 
                transparent=False, coastline=False, projection=None):
    """
    """    
    sizexy_ratio = ndarray.lon.shape[0] / ndarray.lat.shape[0]
    if 'level' in ndarray.coords:
        cols = ndarray.level.shape[0]
    else:
        cols = 1
    rows = ndarray.time.shape[0]
    figcols = cols * 2  
    figrows = rows * 2 
    colorbarzone = 1.4 if show_colorbar else 0
    figsize = (max(8, figcols) * sizexy_ratio * colorbarzone, max(8, figrows))
    fig, ax = subplots(rows, cols, sharex='col', sharey='row', dpi=dpi, 
                       figsize=figsize, constrained_layout=False)

    ndarray = np.squeeze(ndarray)
    for i in range(rows):
        for j in range(cols):
            if cols == 1:
                axis = ax[i]
                image = ndarray[i]
                time = np.datetime64(image.time.values, 'm')
                axis.set_title(f'$\ittime$={time}', fontsize=10)
            elif rows == 1:
                axis = ax[j]
                image = ndarray[j]
                level = image.level.values
                axis.set_title(f'$\itlevel$={level}', fontsize=10)
            else:
                axis = ax[i, j]
                image = ndarray[i, j]
                time = np.datetime64(image.time.values, 'm')
                level = image.level.values
                axis.set_title(f'$\ittime$={time}, $\itlevel$={level}', 
                               fontsize=10)

            if logscale:
                image += np.abs(image.min())
                if vmin is None:
                    linthresh = 1e-2
                else:
                    linthresh = vmin
                    norm = colors.SymLogNorm(linthresh)   
            else:
                norm = None

            im = axis.imshow(image,cmap=cmap, origin='lower', norm=norm,
                             interpolation='nearest', vmin=vmin, vmax=vmax)

            if show_colorbar:
                divider = make_axes_locatable(axis)
                # the width of cax is 2% of axis and the padding between cax
                # and ax wis fixed at 0.05 inch
                cax = divider.append_axes("right", size="2%", pad=0.05)
                cb = fig.colorbar(im, ax=axis, cax=cax, drawedges=False)
                cb.outline.set_linewidth(0.1)
                cb.ax.tick_params(labelsize=8)
                cb.set_label(f'[{ndarray.units}]', rotation=270, labelpad=10)

            if j == 0:
                axis.set_ylabel("$\it{lat}$", fontsize=10)
            if i == rows - 1:
                axis.set_xlabel("$\it{lon}$", fontsize=10)

            if not show_axis:
                axis.set_axis_off()

    if save is not None and isinstance(save, str):
        savefig(save, dpi=dpi, bbox_inches='tight', pad_inches=0,
                transparent=transparent)
        close()
    else:
        show()


def lon_wrap_slice(ds, wrap=360, dim='lon', indices=(-25,45)):
    """
    wrap selection assuming 360 degrees. xarray core is not likely to include 
    this. Shame as would make nice method. Maybe someone builds something on 
    xarray that supports geographical co-ordinates..
    
    Parameters
    ----------
    :param ds: dataset
    :param wrap: default 360 -- period of co-ordinate.
    
    Notes
    -----
    https://github.com/pangeo-data/pangeo/issues/670
    https://gis.stackexchange.com/questions/205871/xarray-slicing-across-the-antimeridian

    # adjust the coordinate system of your data so it is centered over the anti-meridian instead
    # https://gis.stackexchange.com/questions/205871/xarray-slicing-across-the-antimeridian
    # t2m_83 = t2m_83.assign_coords(lon=(t2m_83.lon % 360)).roll(lon=(t2m_83.dims['lon'] // 2))

    """    
    sliceObj = slice(*indices)

    l = (ds[dim] + 2 * wrap) % wrap
    lstart = (sliceObj.start + 2 * wrap) % wrap
    lstop = (sliceObj.stop + 2 * wrap) % wrap
    if lstop > lstart:
        ind = (l <= lstop) & (l >= lstart)
    else:
        ind = (l <= lstop) | (l >= lstart)

    result = ds.isel(**{dim: ind})

    # need to make data contigious which may require rolling it and adjusting 
    # co-ord values.

    # step 1 work out how much to roll co-ordinate system. Need to find "break"
    # break is last place in array where ind goes from False to True
    brk = np.max(np.where(ind.values[:-1] != ind.values[1:]))
    brk = len(l) - brk - 1
    result = result.roll(**{dim: brk})
    # step 2 fix co-ords
    v = result[dim].values
    v = np.where(v < 180., v, v - 360)
    result = result.assign_coords(**{dim: v})

    return result
