export async function resolve(specifier, context, nextResolve) {
  try {
    return await nextResolve(specifier, context);
  } catch (error) {
    if (
      context.parentURL
      && specifier.startsWith(".")
      && !specifier.endsWith(".js")
      && error?.code === "ERR_MODULE_NOT_FOUND"
    ) {
      return nextResolve(`${specifier}.js`, context);
    }
    throw error;
  }
}
