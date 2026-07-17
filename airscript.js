var sheet = Application.Sheets.Item('模组详情');
var sheetmain = Application.Sheets.Item('主页');
var modIds_range = sheet.Range('B2:B' + sheet.UsedRange.Rows.Count);
var modIds = modIds_range.Value();
var platforms_range = sheet.Range('C2:C' + sheet.UsedRange.Rows.Count);
var platforms = platforms_range.Value();
var targetVersion = sheetmain.Range('B6').Value();

function compareMinecraftVersionsDescending(a, b) {
  var aParts = a.split('.').map(Number);
  var bParts = b.split('.').map(Number);
  var partCount = Math.max(aParts.length, bParts.length);

  for (var i = 0; i < partCount; i++) {
    var aPart = aParts[i] || 0;
    var bPart = bParts[i] || 0;
    if (aPart !== bPart) {
      return bPart - aPart;
    }
  }

  return 0;
}

function getGithubVifVersions(repo) {
  var url = 'https://api.github.com/repos/' + repo + '/releases?per_page=30';
  var response = HTTP.fetch(url);
  var releases = response.json();

  if (!Array.isArray(releases)) {
    return [];
  }

  var versions = [];
  for (var i = 0; i < releases.length; i++) {
    var assets = releases[i].assets || [];
    for (var j = 0; j < assets.length; j++) {
      var assetName = assets[j].name || '';
      if (!assetName.toLowerCase().endsWith('.jar')) {
        continue;
      }

      var match = assetName.match(/mc([0-9]+(?:\.[0-9]+)+)/i);
      if (match && versions.indexOf(match[1]) === -1) {
        versions.push(match[1]);
      }
    }
  }

  versions.sort(compareMinecraftVersionsDescending);
  return versions.slice(0, 3);
}

// var infStatus = HTTP.fetch('https://api.mcsrvstat.us/3/inf.dhwpcs.org').json();
// sheetmain.Range('B7').Value(null, infStatus.version)

var mcUrl='https://launchermeta.mojang.com/mc/game/version_manifest.json';
var mcResponse = HTTP.fetch(mcUrl);
var mcData = mcResponse.json();
var latestMcVersion = mcData.latest.release;
sheetmain.Range('B5').Value(null, latestMcVersion);

for (var i = 0; i < modIds.length; i++) {
  var modId = modIds[i][0];
  var platform = platforms[i][0];
  if (platform == 'modrinth') {
    var url = 'https://api.modrinth.com/v2/search?query=' + modId;
    var response = HTTP.fetch(url);
    var data = response.json();

    for (var j = 0; j < data.hits.length; j++) {
      var hit = data.hits[j];
      // 精确匹配mod
      if (hit.slug === modId) {
        var versions = hit.versions;
        versions = (versions.filter(version => !version.includes('w'))).filter(version => !version.includes('-'));
        var latestVersions = versions.slice(-3).reverse();
        sheet.Range('A' + (i + 2)).Value(null, hit.title);
        // if (versions.includes(targetVersion) && targetVersion != latestVersion) {
        //   sheet.Range('C' + (i + 2)).Value(null, targetVersion + '+');
        // } else {
        //   sheet.Range('C' + (i + 2)).Value(null, latestVersion);
        // }
        sheet.Range('D' + (i + 2)).Value(null, latestVersions.join(', '));

        break;
      }
    }
  } else if (platform == 'github-vif') {
    // github-vif 的模组 ID 必须使用完整的 GitHub 仓库路径，例如 Fallen-Breath/pca-protocol。
    try {
      var githubVersions = getGithubVifVersions(modId);
      if (githubVersions.length > 0) {
        sheet.Range('D' + (i + 2)).Value(null, githubVersions.join(', '));
      }
    } catch (error) {
      // 请求失败或响应异常时保留单元格原值，并继续刷新其他模组。
    }
  }
}

function timeInUtc8() {
    const now = new Date();

    // 使用中文格式化选项
    const options = {
        year: 'numeric',
        month: '2-digit',
        day: '2-digit',
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit',
        hour12: false,
        timeZone: 'Asia/Shanghai' // GMT+8
    };

    const formatted = now.toLocaleString('zh-CN', options);

    const [datePart, timePart] = formatted.split(' ');
    const [year, month, day] = datePart.split('/');

    return `${year}年${month}月${day}日 ${timePart}`;
}

sheetmain.Range('B3').Value(null, timeInUtc8());
