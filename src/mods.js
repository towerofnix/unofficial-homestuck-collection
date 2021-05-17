import fs from 'fs'
import path from 'path'

const Store = require('electron-store')
const store = new Store()

const log = require('electron-log');
const logger = log.scope('Mods');

const assetDir = store.has('localData.assetDir') ? store.get('localData.assetDir') : undefined
const modsDir = path.join(assetDir, "mods")
const modsAssetsRoot = "assets://mods/"

var modChoices
var routes = undefined

function getAssetRoute(url) {
  // If the asset url `url` should be replaced by a mod file,
  // returns the path of the mod file. 
  // Otherwise, returns undefined.

  // Lazily bake routes as needed instead of a init hook
  if (routes == undefined) bakeRoutes()

  console.assert(url.startsWith("assets://"), "mods", url)

  const file_route = routes[url]
  if (file_route) logger.debug(url, "to", file_route)
  return file_route
}

function getTreeRoutes(tree, parent=""){
  let routes = []
  for (const name in tree) {
    const dirent = tree[name]
    const subpath = (parent ? parent + "/" + name : name)
    if (dirent == true) {
      // Path points to a file of some sort
      routes.push(subpath)
    } else {
      // Recurse through subpaths
      routes = routes.concat(getTreeRoutes(dirent, subpath))
    }
  }
  return routes
}

function onModLoadFail(enabled_mods, e) {
  logger.info("Mod load failure with modlist", enabled_mods)
  logger.debug(e)
  clearEnabledMods()
  logger.debug("Modlist cleared.")
  // TODO: Replace this with a good visual traceback so users can diagnose mod issues
  throw e 
}

function bakeRoutes() {
  const enabled_mods = getEnabledMods()
  logger.info("Baking routes for", enabled_mods)
  let all_mod_routes = {}
  // Start with least-priority so they're overwritten
  getEnabledModsJs().reverse().forEach(js => {
    try {
      const mod_root = path.join(modsDir, js._id)
      const mod_root_url = new URL(js._id, modsAssetsRoot).href + "/"

      // Lower priority: Auto routes
      if (js.trees) {
        console.assert(!js._singlefile, js.title, "Single file mods cannot use treeroute!")
        
        for (const mod_tree in js.trees) {
          const asset_tree = js.trees[mod_tree] 

          console.assert(mod_tree.endsWith("/"), mod_tree, "Tree paths must be directories! (end with /)")
          console.assert(asset_tree.endsWith("/"), asset_tree, "Tree paths must be directories! (end with /)")
          console.assert(asset_tree.startsWith("assets://"), asset_tree, "Asset paths must be on the assets:// protocol!")

          const treeroutes = getTreeRoutes(crawlFileTree(path.join(mod_root, mod_tree), true))
          treeroutes.forEach(route => {
            all_mod_routes[asset_tree + route] =
              new URL(path.posix.join(mod_tree, route), mod_root_url).href
          })
        }
      }
      
      // Higher priority: manual routes
      for (const key in js.routes || {}) {
        const local = new URL(js.routes[key], mod_root_url).href
        console.assert(!(js._singlefile && local.includes(mod_root_url)), js.title, "Single file mods cannot use local route!")
                
        all_mod_routes[key] = local
      }
    } catch (e) {
      logger.error(e)
    }
  })
  
  // Modify script-global `routes`
  routes = all_mod_routes

  // Test routes
  // TODO: This is super wasteful and should only be done when developer mode is on.
  try {
    const Resources = require("@/resources.js")
    Object.keys(all_mod_routes).forEach(url => {
      Resources.resolveURL(url)
    })
  } catch (e) {
    onModLoadFail(enabled_mods, e)
  }
}

const store_modlist_key = 'localData.settings.modListEnabled'

function getEnabledMods() {
  // Get modListEnabled from settings, even if vue is not loaded yet.
  const list = store.has(store_modlist_key) ? store.get(store_modlist_key) : []
  return list
}

function clearEnabledMods() {
  // TODO: This doesn't trigger the settings.modListEnabled observer,
  // which results in bad settings-screen side effects
  store.set(store_modlist_key, [])
  bakeRoutes()
}

function getEnabledModsJs() {
  return getEnabledMods().map((dir) => getModJs(dir))
}

function crawlFileTree(root, recursive=false) {
  // Gives a object that represents the file tree, starting at root
  // Values are objects for directories or true for files that exist
  const dir = fs.opendirSync(root)
  let ret = {}
  let dirent
  while (dirent = dir.readSync()) {
    if (dirent.isDirectory()) {
      if (recursive) {
        const subpath = path.join(root, dirent.name)
        ret[dirent.name] = crawlFileTree(subpath, true)
      } else { // Is directory, but not doing a recursive scan
        ret[dirent.name] = []
      }
    } else { // Not a directory
      ret[dirent.name] = true
    }
  }
  dir.close()
  return ret
}

function getModJs(mod_dir, singlefile=false) {
  // Tries to load a mod from a directory
  // If mod_dir/mod.js is not found, tries to load mod_dir.js as a single file
  // Errors passed to onModLoadFail and raised
  try {
    let modjs_path
    if (singlefile) {
      modjs_path = path.join(modsDir, mod_dir)
    } else {
      modjs_path = path.join(modsDir, mod_dir, "mod.js")
    }
    var mod = __non_webpack_require__(modjs_path)
    mod._id = mod_dir
    mod._singlefile = singlefile
    return mod
  } catch (e1) {
    // elaborate error checking w/ afllback
    const e1_is_notfound = (e1.code && e1.code == "MODULE_NOT_FOUND")
    if (singlefile) {
      if (e1_is_notfound) {
        // Tried singlefile, missing
        throw e1
      } else {
        // Singlefile found, other error
        logger.error("Singlefile found, other error 1")
        onModLoadFail([mod_dir], e1)
        throw e1
      }
    } else if (e1_is_notfound) {
      // Tried dir/mod.js, missing
      try {
        // Try to find singlefile
        return getModJs(mod_dir, true)
      } catch (e2) {
        const e2_is_notfound = (e2.code && e2.code == "MODULE_NOT_FOUND")
        if (e2_is_notfound) {
          // Singlefile not found either
          logger.error(mod_dir, "is missing required file 'mod.js'")
          onModLoadFail([mod_dir], e2)
        } else {
          logger.error("Singlefile found, other error 2")
          onModLoadFail([mod_dir], e2)
        } 
        // finally
        throw e2
      }
    } else {
      // dir/mod.js found, other error
      onModLoadFail([mod_dir], e1)
      throw e1
    }
  }
}

// Interface

function editArchive(archive) {
  getEnabledModsJs().reverse().forEach((js) => {
    const editfn = js.edit
    if (editfn) {
      archive = editfn(archive)
    }
  })
}

function getMainMixin(){
  // A mixin that injects on the main vue process.
  // Currently this just injects custom css

  let styles = []
  getEnabledModsJs().forEach(js => {
    const mod_root_url = new URL(js._id, modsAssetsRoot).href + "/"
    const modstyles = js.styles || []
    modstyles.forEach(style_link => styles.push(new URL(style_link, mod_root_url).href))
  })

  return {
    mounted() {
      logger.debug("Mounted main mixin")

      styles.forEach((style_link) => {
        const link = document.createElement("link")
        link.rel = "stylesheet"
        link.type = "text/css"
        link.href = style_link

        this.$el.appendChild(link)
        logger.debug(link)
      })
    }
  }
}

function getMixins(){
  // This is absolutely black magic
  const nop = () => undefined

  return getEnabledModsJs().reverse().map((js) => {
    const vueHooks = js.vueHooks || []
    var mixin = {
      created() {
        // Normally mixins are ignored on name collision
        // We need to do the opposite of that, so we hook `created`
        vueHooks.forEach((hook) => {
          // Shorthand
          if (hook.matchName) {
            hook.match = (c) => (c.$options.name == hook.matchName)
          }

          if (hook.match(this)) {
            for (const cname in (hook.computed || {})) {
              // Precomputed super function
              // eslint-disable-next-line no-extra-parens
              const sup = (() => this._computedWatchers[cname].getter.call(this) || nop);
              Object.defineProperty(this, cname, {
                get: () => (hook.computed[cname](sup)),
                configurable: true
              })
            }
            for (const dname in (hook.data || {})) {
              const value = hook.data[dname]
              this[dname] = (typeof value == "function" ? value(this[dname]) : value)
            }
          }
        })
      }
    }
    return mixin
  })
}

// Runtime
// Grey magic. This file can be run from either process, but only the main process will do file handling.
const {ipcMain, ipcRenderer} = require('electron')
if (ipcMain) {
  // We are in the main process.
  function loadModChoices(){
    // Get the list of mods players can choose to enable/disable
    var mod_folders
    try {
      // TODO: Replace this with proper file globbing
      const tree = crawlFileTree(modsDir, false)
      // .js file or folder of some sort
      mod_folders = Object.keys(tree).filter(p => /\.js$/.test(p) || tree[p] == [])
    } catch (e) {
      // No mod folder at all. That's okay.
      logger.error(e)
      return []
    }
    var items = mod_folders.reduce((acc, dir) => {
      try {
        const js = getModJs(dir)
        acc[dir] = {
          label: js.title,
          desc: js.desc,
          key: dir
        }
      } catch (e) {
        // Catch import-time mod-level errors
        logger.error(e)
      }
      return acc
    }, {})
    // logger.info("Mod choices loaded")
    // logger.debug(items)
    return items
  }

  modChoices = loadModChoices()

  ipcMain.on('GET_AVAILABLE_MODS', (e) => {e.returnValue = modChoices})
} else {
  // We are in the renderer process.
  modChoices = ipcRenderer.sendSync('GET_AVAILABLE_MODS')
}

export default {
  getEnabledModsJs,  // probably shouldn't use
  getEnabledMods,
  getMixins,
  getMainMixin,
  editArchive,
  bakeRoutes,
  getAssetRoute,

  modChoices
}
