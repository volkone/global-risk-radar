/* Static Pages data requests share a timeout and bypass browser caching. */
window.getRadarData = async function (path) {
  const response = await fetch('./' + path + '?' + Date.now(), {
    cache: 'no-store',
    signal: AbortSignal.timeout(12000)
  });
  if (!response.ok) throw new Error(path + ' HTTP ' + response.status);
  return response.json();
};

let foreignCashRankingRequest;
window.getForeignCashRanking = function () {
  foreignCashRankingRequest ??= window.getRadarData('foreign_cash_ranking.json')
    .finally(() => { foreignCashRankingRequest = undefined; });
  return foreignCashRankingRequest;
};
