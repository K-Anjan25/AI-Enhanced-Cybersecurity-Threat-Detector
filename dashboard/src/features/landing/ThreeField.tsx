import { useEffect, useRef } from 'react';

/**
 * Background scene for the landing hero, drawn with three.js.
 *
 * A particle field and three wireframe shells sit at different depths. The camera
 * moves with scroll and drifts with the pointer, so the layers separate as the page
 * scrolls. three is loaded on demand so it stays out of the main bundle. If WebGL is
 * unavailable, or the user prefers reduced motion, the scene draws one still frame or
 * nothing at all, and the page content is unaffected.
 */

export function ThreeField({ className = '' }: { className?: string }) {
  const hostRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const host = hostRef.current;
    if (!host) return undefined;

    let disposed = false;
    let teardown: (() => void) | undefined;
    const reduceMotion = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches === true;

    void import('three')
      .then((THREE) => {
        if (disposed) return;

        let renderer: InstanceType<typeof THREE.WebGLRenderer>;
        try {
          renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
        } catch {
          return; // No WebGL: the page still works without the background.
        }
        renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
        renderer.domElement.setAttribute('aria-hidden', 'true');
        host.appendChild(renderer.domElement);

        // The accent comes from the token file; white is used only if the token is absent.
        const accentCss = getComputedStyle(document.documentElement)
          .getPropertyValue('--color-accent')
          .trim();
        const accent = accentCss ? new THREE.Color(accentCss) : new THREE.Color(0xffffff);

        const scene = new THREE.Scene();
        const camera = new THREE.PerspectiveCamera(55, 1, 0.1, 200);
        camera.position.set(0, 0, 14);

        // Layer 1 (far): a dense particle field.
        const count = 1600;
        const positions = new Float32Array(count * 3);
        for (let i = 0; i < count; i += 1) {
          positions[i * 3] = (Math.random() - 0.5) * 34;
          positions[i * 3 + 1] = (Math.random() - 0.5) * 18;
          positions[i * 3 + 2] = -Math.random() * 30 + 6;
        }
        const pointGeometry = new THREE.BufferGeometry();
        pointGeometry.setAttribute('position', new THREE.BufferAttribute(positions, 3));
        const points = new THREE.Points(
          pointGeometry,
          new THREE.PointsMaterial({
            color: accent,
            size: 0.05,
            transparent: true,
            opacity: 0.7,
            depthWrite: false,
          }),
        );
        scene.add(points);

        // Layers 2 to 4: wireframe shells at increasing distance from the camera.
        const shells: Array<{ mesh: InstanceType<typeof THREE.LineSegments>; speed: number }> = [];
        const shellSpecs = [
          { radius: 2.4, z: 1.5, speed: 0.25, opacity: 0.55 },
          { radius: 4.2, z: -3.5, speed: -0.15, opacity: 0.35 },
          { radius: 6.5, z: -9, speed: 0.08, opacity: 0.2 },
        ];
        for (const spec of shellSpecs) {
          const geometry = new THREE.WireframeGeometry(
            new THREE.IcosahedronGeometry(spec.radius, 1),
          );
          const mesh = new THREE.LineSegments(
            geometry,
            new THREE.LineBasicMaterial({
              color: accent,
              transparent: true,
              opacity: spec.opacity,
              depthWrite: false,
            }),
          );
          mesh.position.z = spec.z;
          scene.add(mesh);
          shells.push({ mesh, speed: spec.speed });
        }

        const pointer = { x: 0, y: 0 };
        const onPointer = (event: PointerEvent) => {
          pointer.x = (event.clientX / window.innerWidth - 0.5) * 2;
          pointer.y = (event.clientY / window.innerHeight - 0.5) * 2;
        };
        window.addEventListener('pointermove', onPointer, { passive: true });

        const resize = () => {
          const width = host.clientWidth || 1;
          const height = host.clientHeight || 1;
          renderer.setSize(width, height, false);
          camera.aspect = width / height;
          camera.updateProjectionMatrix();
        };
        resize();
        const observer = new ResizeObserver(resize);
        observer.observe(host);

        const render = (time: number) => {
          const progress = Math.min(window.scrollY / Math.max(window.innerHeight, 1), 1.5);
          const t = time / 1000;
          camera.position.z = 14 - progress * 4;
          camera.position.y = -progress * 2.5;
          camera.position.x += (pointer.x * 1.4 - camera.position.x) * 0.04;
          camera.lookAt(0, 0, 0);
          points.rotation.y = t * 0.02;
          for (const shell of shells) {
            shell.mesh.rotation.x = t * shell.speed * 0.6;
            shell.mesh.rotation.y = t * shell.speed;
          }
          renderer.render(scene, camera);
        };

        let frame = 0;
        if (reduceMotion) {
          render(0);
        } else {
          const loop = (time: number) => {
            render(time);
            frame = requestAnimationFrame(loop);
          };
          frame = requestAnimationFrame(loop);
        }
        const onScroll = () => {
          if (reduceMotion) render(0);
        };
        window.addEventListener('scroll', onScroll, { passive: true });

        teardown = () => {
          cancelAnimationFrame(frame);
          window.removeEventListener('scroll', onScroll);
          window.removeEventListener('pointermove', onPointer);
          observer.disconnect();
          pointGeometry.dispose();
          (points.material as InstanceType<typeof THREE.Material>).dispose();
          for (const shell of shells) {
            shell.mesh.geometry.dispose();
            (shell.mesh.material as InstanceType<typeof THREE.Material>).dispose();
          }
          renderer.dispose();
          renderer.domElement.remove();
        };
      })
      .catch(() => {
        // The chunk failed to load; the hero simply has no background.
      });

    return () => {
      disposed = true;
      teardown?.();
    };
  }, []);

  return <div ref={hostRef} aria-hidden="true" className={`absolute inset-0 ${className}`} />;
}
