import fs from "fs";
import path from "path";

const root = process.cwd();

const copies = [
  {
    from: path.join(root, "node_modules", "leaflet", "dist", "leaflet.css"),
    to: path.join(root, "static", "vendor", "leaflet", "leaflet.css"),
  },
  {
    from: path.join(root, "node_modules", "leaflet", "dist", "leaflet.js"),
    to: path.join(root, "static", "vendor", "leaflet", "leaflet.js"),
  },
  {
    from: path.join(root, "node_modules", "leaflet", "dist", "images"),
    to: path.join(root, "static", "vendor", "leaflet", "images"),
    isDir: true,
  },
  {
    from: path.join(root, "node_modules", "swiper", "swiper-bundle.min.css"),
    to: path.join(root, "static", "vendor", "swiper", "swiper-bundle.min.css"),
  },
  {
    from: path.join(root, "node_modules", "swiper", "swiper-bundle.min.js"),
    to: path.join(root, "static", "vendor", "swiper", "swiper-bundle.min.js"),
  },
];

function ensureDir(dirPath) {
  fs.mkdirSync(dirPath, { recursive: true });
}

function copyFile(from, to) {
  ensureDir(path.dirname(to));
  fs.copyFileSync(from, to);
  console.log(`copied: ${from} -> ${to}`);
}

function copyDir(from, to) {
  ensureDir(to);
  for (const entry of fs.readdirSync(from, { withFileTypes: true })) {
    const src = path.join(from, entry.name);
    const dst = path.join(to, entry.name);
    if (entry.isDirectory()) {
      copyDir(src, dst);
    } else {
      copyFile(src, dst);
    }
  }
}

for (const item of copies) {
  if (!fs.existsSync(item.from)) {
    console.error(`missing: ${item.from}`);
    process.exitCode = 1;
    continue;
  }

  if (item.isDir) {
    copyDir(item.from, item.to);
  } else {
    copyFile(item.from, item.to);
  }
}