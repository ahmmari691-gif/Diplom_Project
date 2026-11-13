// Public navigation stays in the same business, even with an owner session.
export function storefrontHref(search = '') {
  const params = new URLSearchParams(search);
  let business = params.get('b');
  if (!business) {
    const match = (params.get('track') || '').match(/^[a-f0-9-]{36}\.([a-f0-9]{32})$/);
    business = match?.[1];
  }
  if (!/^[a-f0-9]{32}$/.test(business || '')) return '/';
  const target = new URLSearchParams({b: business});
  for (const name of ['utm_source', 'utm_campaign']) {
    if (params.get(name)) target.set(name, params.get(name));
  }
  return '/?' + target.toString();
}

export function privacyHref(search = '') {
  const target = storefrontHref(search);
  const params = new URLSearchParams(target.split('?')[1] || '');
  params.set('privacy', '1');
  return '/?' + params.toString();
}
