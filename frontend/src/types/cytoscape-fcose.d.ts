// No published types for cytoscape-fcose; minimal ambient declaration for
// the one thing we use it for (registering the layout extension).
declare module "cytoscape-fcose" {
  import type * as cytoscape from "cytoscape";

  const fcose: cytoscape.Ext;
  export default fcose;
}
