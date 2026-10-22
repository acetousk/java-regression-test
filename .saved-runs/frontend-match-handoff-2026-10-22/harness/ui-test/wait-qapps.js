// Qapps updates history before its nested screen components finish loading.
// Network-idle alone can occur between those loads. Observe Vue/DOM completion.
async function waitQapps(page, route, timeout = 15000) {
  await page.evaluate(({ route, timeout }) => new Promise((resolve, reject) => {
    const vm = window.moqui?.webrootVue;
    if (!vm) return reject(new Error('Qapps Vue root is missing'));
    const target = '/' + route.split('?')[0];
    let unwatch;
    let observer;
    const finish = error => {
      clearTimeout(timer);
      unwatch?.();
      observer?.disconnect();
      if (error) reject(error); else resolve();
    };
    const timer = setTimeout(() => finish(new Error(`Qapps screen did not finish loading: ${target}`)), timeout);
    const check = () => vm.$nextTick(() => {
      const paths = vm.currentPathList || [];
      const active = vm.activeSubscreens || [];
      if (vm.loading !== 0 || !vm.currentPath?.endsWith(target) || !paths.length ||
          active.length < paths.length || paths.some((name, i) => active[i]?.pathName !== name) ||
          document.querySelector('#current-page-root > .spinner')) return;
      finish();
    });
    unwatch = vm.$watch(() => [vm.loading, vm.currentPath, vm.activeSubscreens.length].join('|'), check);
    observer = new MutationObserver(check);
    observer.observe(document.body, { childList: true, subtree: true });
    check();
  }), { route, timeout });
}
module.exports = { waitQapps };
