import React from "react";

export const AvatarPlaceholder = (props: { style: any }) => (
  <svg
    viewBox="0 0 365 365"
    fill="none"
    {...props}
    role="img"
    aria-label="Avatar placeholder"
  >
    <path fill="#9473B0" d="M0 0h365v365H0z" />
    <path stroke="#000" d="M0 0h365v365H0z" />
    <path fill="#F8B03D" d="M118.344 213.943h124.365v151.943H118.344z" />
    <path
      d="M242.35 366.674V209.722H119.227v156.952"
      stroke="#000"
      strokeWidth={4}
      strokeMiterlimit={10}
    />
    <path
      d="M161.671 248.57v47.155l20.04-20.045 18.829 18.862v-47.328"
      fill="#EA4136"
    />
    <path
      d="M161.671 248.57v47.155l20.04-20.045 18.829 18.862v-47.328"
      stroke="#000"
      strokeWidth={4}
      strokeMiterlimit={10}
    />
    <path
      d="M181.105 250.56c44.558 0 80.679-42.585 80.679-95.117 0-52.532-36.121-95.117-80.679-95.117s-80.679 42.585-80.679 95.117c0 52.532 36.121 95.117 80.679 95.117z"
      fill="#F8B03D"
      stroke="#000"
      strokeWidth={4}
      strokeMiterlimit={10}
    />
    <path
      d="M153.02 162.682c5.335 0 9.66-4.326 9.66-9.662 0-5.336-4.325-9.661-9.66-9.661-5.334 0-9.659 4.325-9.659 9.661 0 5.336 4.325 9.662 9.659 9.662zM206.133 162.682c5.335 0 9.66-4.326 9.66-9.662 0-5.336-4.325-9.661-9.66-9.661s-9.659 4.325-9.659 9.661c0 5.336 4.324 9.662 9.659 9.662z"
      fill="#000"
    />
  </svg>
);
