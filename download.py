import requests, yaml, os

modConfig = yaml.safe_load(open('mods.yaml'))

def getModFromModrinth(id, modLoader, mcVersion, versionType='release'):
    r = requests.get(f'https://api.modrinth.com/v2/project/{id}/version?loaders=["{modLoader}"]&game_versions=["{mcVersion}"]')
    versions = r.json()
    if versions:
        releases = [x for x in versions if x['version_type'] == versionType]
        if releases:
            return releases[0]['files'][0]['filename'], releases[0]['files'][0]['url']
    return None

os.makedirs('mods', exist_ok=True)

for mod in modConfig['mods']:
    filename, url = None, None
    print(mod['id'], mod['type'])

    if mod['type'] == 'modrinth':
        found = False
        mod_id = mod['id']
        loader = modConfig['modLoader']
        current_version = modConfig['mcVersion']
        version_type = mod.get('versionType', 'release')
        modFile = getModFromModrinth(mod_id, loader, current_version, version_type)
        if modFile:
            filename, url = modFile
            found = True
        else:
            modFile = getModFromModrinth(mod_id, loader, current_version, 'beta')
            if modFile:
                filename, url = modFile
                found = True
                print(f'!! Found beta version for {mod_id} on {current_version}')
        if not found and 'mcCompatibles' in modConfig:
            for mcVersion in modConfig['mcCompatibles']:
                modFile = getModFromModrinth(mod_id, loader, mcVersion, version_type)
                if not modFile:
                    modFile = getModFromModrinth(mod_id, loader, mcVersion, 'beta')
                if modFile:
                    print(f'!! Found mod for {mod_id} on compatible version {mcVersion}')
                    found = True
                    break
            else:
                print(f'Failed to find mod {mod_id} in any version')
                continue
        filename, url = modFile
    elif mod['type'] == 'github' and mod.get('repo'):
        r = requests.get(f'https://api.github.com/repos/{mod["repo"]}/releases')
        releases = r.json()
        versionInFileName, releaseFilter, versionInRelease = False, None, False
        if mod.get('releaseFilter'):
            releases = [x for x in releases if mod['releaseFilter'] in x['name']]
            if releases:
                jarFile = [x for x in releases[0]['assets'] if x['name'].endswith('.jar')]
                if jarFile:
                    filename, url = jarFile[0]['name'], jarFile[0]['browser_download_url']
        elif mod.get('versionInRelease'):
            releases = [x for x in releases if modConfig['mcVersion'] in x['name']]
            if releases:
                jarFile = [x for x in releases[0]['assets'] if x['name'].endswith('.jar')]
                if jarFile:
                    filename, url = jarFile[0]['name'], jarFile[0]['browser_download_url']
            else:
                for version in modConfig['mcCompatibles']:
                    releases = [x for x in releases if version in x['name']]
                    if releases:
                        jarFile = [x for x in releases[0]['assets'] if x['name'].endswith('.jar')]
                        if jarFile:
                            filename, url = jarFile[0]['name'], jarFile[0]['browser_download_url']
                            print(f'!! Found mod using compatible version {version}')
                        break
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