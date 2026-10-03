import { Suspense } from "react";
import { HomeView } from "@/components/home/HomeView";

export default function Page() {
  return (
    <Suspense fallback={null}>
      <HomeView />
    </Suspense>
  );
}
