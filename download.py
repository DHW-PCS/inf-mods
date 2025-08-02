import requests, yaml

modConfig = yaml.safe_load(open('mods.yaml'))

def getModFromModrinth(id, modLoader, mcVersion, versionType='release'):
    r = requests.get(f'https://api.modrinth.com/v2/project/{id}/version?loaders=["{modLoader}"]&game_versions=["{mcVersion}"]')
    versions = r.json()
    if versions:
        releases = [x for x in versions if x['version_type'] == versionType]
        if releases:
            return releases[0]['files'][0]['filename'], releases[0]['files'][0]['url']
    return None

for mod in modConfig['mods']:
    filename, url = None, None
    print(mod['id'], mod['type'])
    if mod['type'] == 'modrinth':
        modFile = getModFromModrinth(
            mod['id'],
            modConfig['modLoader'],
            modConfig['mcVersion'],
            mod.get('versionType', 'release')
        )
        if not modFile:
            modFile = getModFromModrinth(
                mod['id'],
                modConfig['modLoader'],
                modConfig['mcVersion'],
                'beta'
            )
            print(f'!! Found beta version for {mod["id"]}')
        if not modFile and 'mcCompatibles' in modConfig:
            for mcVersion in modConfig['mcCompatibles']:
                version_type = mod.get('versionType', 'release')
                modFile = getModFromModrinth(
                    mod['id'],
                    modConfig['modLoader'],
                    mcVersion,
                    version_type
                )
                if modFile:
                    print(f'!! Found mod for {mcVersion} using compatible version {mcVersion}')
                    filename, url = modFile
                    break
            else:
                print(f'!! Failed to find mod {mod["id"]} in any compatible version')
                continue
        elif not modFile:
            print(f'!! Failed to find mod {mod["id"]} for Minecraft {modConfig["mcVersion"]}')
            continue
        filename, url = modFile
    elif mod['type'] == 'github' and mod.get('repo'):
        r = requests.get(f'https://api.github.com/repos/{mod["repo"]}/releases')
        releases = r.json()
        versionFilter, releaseFilter = None, None
        if mod.get('releaseFilter'):
            releases = [x for x in releases if mod['releaseFilter'] in x['name']]
            if releases:
                jarFile = [x for x in releases[0]['assets'] if x['name'].endswith('.jar')]
                if jarFile:
                    filename, url = jarFile[0]['name'], jarFile[0]['browser_download_url']
        elif mod.get('versionInFileName'):
            versionFilter = modConfig['mcVersion']
        elif mod.get('versionFilter'):
            versionFilter = mod['versionFilter']
        if versionFilter:
            for release in releases:
                for asset in release['assets']:
                    if versionFilter in asset['name']:
                        filename, url = asset['name'], asset['browser_download_url']
                        break
                if filename:
                    break
            if not filename and 'mcCompatibles' in modConfig:
                for mcVersion in modConfig['mcCompatibles']:
                    for release in releases:
                        for asset in release['assets']:
                            if mcVersion in asset['name']:
                                filename, url = asset['name'], asset['browser_download_url']
                                break
                        if filename:
                            break
                    if filename:
                        print(f'!! Found mod using compatible version {mcVersion}')
                        break
    if filename and url:
        print(filename, url)
        r = requests.get(url, allow_redirects=True)
        open('mods/' + filename, 'wb').write(r.content)
    else:
        print('!! Failed to download', mod['id'])